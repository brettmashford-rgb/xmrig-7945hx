"""Actual packed math/fragment equivalence and unchanged lean host lifecycle. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import random
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.b_quad_scan import BQuadBackend,BQuadPaddedBackend,new_b_quad_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class PackedMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name)
        source=folder/'quad.cpp';source.write_text('''#include "b_quad.h"
#include "cached_a_pack.h"
extern "C" unsigned diff(unsigned a,unsigned b){return b_quad_difference(a,b);}
extern "C" unsigned oldword(const signed char*c,const unsigned*p,unsigned r,unsigned o){return cached_b_word(c,p,r,o);}
extern "C" unsigned fragment(const unsigned*c,const unsigned*p,unsigned stride,unsigned offset,unsigned lane,unsigned high,unsigned second){
 unsigned group=lane/4,thread=lane%4,result=0;
 for(unsigned byte=0;byte<4;++byte){unsigned source=b_quad_source(group,thread,byte);
 unsigned pair=p[offset+(source&15)+(second?16:0)];
 unsigned value=b_quad_value(c,stride,pair,(source>>4)+(high?2:0));
 result|=b_quad_pick(value,group,byte);}
 return result;
}
''')
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-unknown-pragmas','-shared','-fPIC','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'quad.so')],check=True)
        cls.lib=C.CDLL(str(folder/'quad.so'));cls.lib.diff.argtypes=[C.c_uint]*2;cls.lib.diff.restype=C.c_uint
        cls.lib.oldword.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint];cls.lib.oldword.restype=C.c_uint
        cls.lib.fragment.argtypes=[C.c_void_p,C.c_void_p]+[C.c_uint]*5;cls.lib.fragment.restype=C.c_uint
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_all_65536_byte_differences_and_cross_lane_carries(self):
        for a in range(256):
            for b in range(256):
                aa=(a,255-a,a^85,a^170);bb=(b,b^85,255-b,b^170)
                pack=lambda values:sum(v<<(8*i)for i,v in enumerate(values))
                expected=pack(tuple((64+x-y)&255 for x,y in zip(aa,bb)))
                self.assertEqual(self.lib.diff(pack(aa),pack(bb)),expected)
    def test_all_lanes_both_halves_both_column_blocks_and_layouts_match_original(self):
        rng=random.Random(52052)
        signed=[rng.randrange(-128,128)for _ in range(128*16)]
        old=bytes((signed[index*16+row]&255)if row<16 else 0 for index in range(128)for row in range(18))
        pairs=tuple(rng.randrange(128)|(rng.randrange(128)<<16)for _ in range(32768));packed=struct.pack('<32768I',*pairs)
        for stride in (4,5):
            words=[sum((signed[index*16+block*4+byte]&255)<<(byte*8)for byte in range(4))if block<4 else 0
                for index in range(128)for block in range(stride)]
            cache=struct.pack('<'+'I'*len(words),*words)
            for offset in (0,32,96,128,16352,16384,32640,32736):
                for lane in range(32):
                    for high in (0,1):
                        for second in (0,1):
                            expected=self.lib.oldword(old,packed,lane//4+high*8,offset+(lane%4)*4+second*16)
                            self.assertEqual(self.lib.fragment(cache,packed,stride,offset,lane,high,second),expected)
    def test_validated_a_mma_transcript_hash_target_queue_body_is_verbatim(self):
        old=(ROOT/'gpu/direct_resident_scan.cu').read_text();new=(ROOT/'gpu/b_quad_scan.cu').read_text()
        a='        unsigned a0=';b='        unsigned b0=';mma='        mma_accumulate'
        self.assertEqual(old[old.index(a):old.index(b)],new[new.index(a):new.index(mma)])
        self.assertEqual(old[old.index(mma):],new[new.index(mma):new.index('extern "C" __global__ void b_quad_packed_scan')].rstrip()+'\n')


class ModuleChecks(unittest.TestCase):
    def test_ptx_has_both_24_argument_entries_without_block_barriers(self):
        import re
        raw=(ROOT/'releases/pearlhash-dev-v0.0.52-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',raw)
        for name in ('b_quad_packed_scan','b_quad_padded_scan'):
            part=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
    def test_driver_jit_resource_attributes_are_queried_outside_kernel_work(self):
        from tools.b_quad_scan import kernel_resources
        values={4:64,1:16384,3:0};seen=[]
        def api(name,types,*args):
            self.assertEqual(name,'cuFuncGetAttribute');self.assertEqual(args[2].value,123)
            seen.append(args[1]);C.cast(args[0],C.POINTER(C.c_int))[0]=values[args[1]]
        dispatch=SimpleNamespace(device=SimpleNamespace(api=api),function=C.c_void_p(123))
        self.assertEqual(kernel_resources(dispatch),dict(registers_per_thread=64,static_shared_bytes=16384,local_bytes_per_thread=0))
        self.assertEqual(seen,[4,1,3])


class Quad(unittest.TestCase):
    padded=False
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        self.backend_type=BQuadPaddedBackend if self.padded else BQuadBackend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=self.backend_type(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_new_entry_has_same_24_slot_abi_and_lean_driver_path(self):
        dispatch=self.backend.dispatch;entry=b'b_quad_padded_scan'if self.padded else b'b_quad_packed_scan'
        self.assertEqual(dispatch.function.value,self.device.functions[entry]);self.assertEqual(len(dispatch.arguments),24)
        self.assertEqual(dispatch.guard_count,28);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.backend(FastBatch(self.plan,0,5),1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2);self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1)
        self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
        self.assertEqual(self.device.reads,[504])
    def test_changed_generation_before_launch_blocks_scanner(self):
        self.gen[0]+=1;self.device.calls.clear()
        with self.assertRaisesRegex(ValueError,'stale'):self.backend(FastBatch(self.plan,0,5),1,self.job.generation)
        self.assertNotIn('cuLaunchKernel',self.device.calls)
    def test_new_search_retains_stale_cursor_cleanup(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_b_quad_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0],padded=self.padded)
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()


class PaddedQuad(Quad):padded=True


if __name__=='__main__':unittest.main()
