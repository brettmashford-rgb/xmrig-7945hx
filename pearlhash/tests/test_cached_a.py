"""A-cache layout, lifecycle, attachment and stale cursor tests. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.cached_a import CachedA,attach,cache_size,new_cached_a_search
from tools.cuda_driver import CudaDevice
from tools.production_scan import ProductionCandidateScanner
from tools.prepared_dispatch import PreparedDispatch,KERNELS
from tools.check_tile_scan_gpu import TileQuery
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_prepared_dispatch import FakeDevice,FakeTables,profile

ROOT=Path(__file__).resolve().parents[1]


class Device(FakeDevice,ProductionCandidateScanner):
    allocate=CudaDevice.allocate
    def api(self,name,types,*args):
        if name=='cuMemAlloc_v2':
            C.cast(args[0],C.POINTER(C.c_ulonglong))[0]=self.next
            self.memory[self.next]=bytearray(args[1]);self.next+=args[1]+64
            self.calls.append(name)
        else:super().api(name,types,*args)
    def launch(self,name,args,blocks,threads):
        if name!=b'materialize_selected_rows':raise AssertionError(name)
        self.materialization=args


class Tables(FakeTables):
    def __init__(self,device,p):super().__init__(device);self.profile=p
    def close(self):self.closed=True


class CacheTests(unittest.TestCase):
    def test_comparison_prefers_new_path_only_after_setup_and_margin(self):
        from tools.check_cached_a import preferred
        self.assertEqual(preferred(1.,.5,.1),'cached-a')
        self.assertEqual(preferred(1.,.5,.6),'baseline')
        self.assertEqual(preferred(1.,.98,0.),'baseline')
        with self.assertRaises(ValueError):preferred(1.,-.1,0.)

    def test_actual_cpp_pack_layout_and_zero_padding(self):
        with tempfile.TemporaryDirectory()as temporary:
            folder=Path(temporary);source=folder/'pack.cpp'
            source.write_text('#include "cached_a_pack.h"\nextern "C" unsigned pack(const signed char*p,unsigned r,unsigned o,int live){return cached_a_word(p,r,o,live);}\n')
            with source.open('a')as output:output.write('extern \"C\" unsigned pack_b(const signed char*p,const unsigned*q,unsigned r,unsigned o){return cached_b_word(p,q,r,o); }\n')
            subprocess.run(['g++','-O2','-shared','-fPIC','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'pack.so')],check=True)
            lib=C.CDLL(str(folder/'pack.so'));lib.pack.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_int];lib.pack.restype=C.c_uint
            raw=bytes((i*7+3)%256 for i in range(3*32768))
            for row in range(3):
                for offset in (0,4,16,32752,32764):
                    self.assertEqual(lib.pack(raw,row,offset,1),int.from_bytes(raw[row*32768+offset:row*32768+offset+4],'little'))
            self.assertEqual(lib.pack(None,0,0,0),0)
            lib.pack_b.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint];lib.pack_b.restype=C.c_uint
            signed=[((i*3+7)%64)-32 for i in range(18*128)]
            cache=bytes(v&255 for v in signed)
            pairs=tuple((i%128)|(((i*7+1)%128)<<16)for i in range(32768))
            packed=struct.pack('<32768I',*pairs)
            for row in (0,7,8,15):
                for offset in (0,16,32764):
                    expected=sum(((64+signed[(pairs[offset+i]&65535)*18+row]-signed[(pairs[offset+i]>>16)*18+row])&255)<<(i*8)for i in range(4))
                    self.assertEqual(lib.pack_b(cache,packed,row,offset),expected)

    def test_all_rows_materialized_without_mutating_original_noise_pointer(self):
        device=Device();p=replace(profile(),m=11,n=17);tables=Tables(device,p)
        unrelated,_=device.guarded(4)
        cache=CachedA(tables);self.assertEqual(cache.bytes,11*32768)
        args=device.materialization
        indices=tables.read(args[5],0,11*4)
        self.assertEqual(struct.unpack('<11I',indices),tuple(range(11)))
        self.assertEqual((args[7].value,args[8].value),(11,0))
        dispatch=PreparedDispatch(device,tables,KERNELS[0],capacity=0)
        original=dispatch.arguments[0];old_value=original.value
        attach(dispatch,cache)
        self.assertIsNot(dispatch.arguments[0],original);self.assertEqual(original.value,old_value)
        self.assertEqual(dispatch.arguments[0].value,cache.pointer.value)
        batch=dispatch.prepare([TileQuery(tuple(range(10)),tuple(range(16)))],[0])
        self.assertEqual(dispatch.run(batch,1).total,0)
        cache.close();cache.close()
        with self.assertRaises(ValueError):dispatch.run(batch,1)
        dispatch.close();self.assertEqual(device.allocations,[unrelated]);self.assertFalse(tables.closed)

    def test_caps_guards_and_foreign_attachment(self):
        self.assertEqual(cache_size(profile()),5121*32768)
        for m in (0,8193,True):
            with self.assertRaises(ValueError):cache_size(SimpleNamespace(m=m,k=32768,rank=128,fill=64))
        device=Device();p=replace(profile(),m=11,n=17);tables=Tables(device,p);cache=CachedA(tables)
        foreign=PreparedDispatch(device,Tables(device,p),KERNELS[0],capacity=0)
        with self.assertRaises(ValueError):attach(foreign,cache)
        data=device.memory[cache.raw.value];data[-1]=0
        with self.assertRaisesRegex(RuntimeError,'guard'):cache.check_guards()
        foreign.close();cache.close();self.assertEqual(device.allocations,[])

    def test_new_engine_windows_and_replacement_release_A_and_dispatch_buffers(self):
        session,job,message=synthetic_session(bytes(32));device=Device()
        context=SimpleNamespace(job=job,profile=replace(profile(),m=160,n=192))
        with patch('tools.prepared_backend.VirtualTables',Tables):
            search=new_cached_a_search(context,device,session.is_current)
            owned=tuple(device.allocations)
            for end in (8,16):
                hit,cursor=search.advance(8);self.assertIsNone(hit);self.assertEqual(cursor.next_tile,end)
                self.assertEqual(tuple(device.allocations),owned)
            device.after_launch=lambda:session.consume(message)
            with self.assertRaises(StaleWork):search.advance(8)
            self.assertEqual(cursor.next_tile,16);self.assertTrue(search.closed)
            self.assertEqual(device.allocations,[])
        session.close()


if __name__=='__main__':unittest.main()
