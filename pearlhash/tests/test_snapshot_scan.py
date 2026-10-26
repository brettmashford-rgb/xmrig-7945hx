"""Packed reads preserve guards, window identity, queue verification and ownership. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.snapshot_scan import SnapshotResidentBackend,SnapshotDirectBackend,new_snapshot_search
from tools.virtual_scan import VirtualTables
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_cached_a import Device,Tables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class SnapshotDevice(Device):
    def __init__(self):
        super().__init__();self.functions={};self.after_snapshot=None;self.reads=[]
    def read_bytes(self,address,size):
        data,off=self.locate(C.c_ulonglong(address),0,size);return bytes(data[off:off+size])
    def write_bytes(self,address,raw):
        data,off=self.locate(C.c_ulonglong(address),0,len(raw));data[off:off+len(raw)]=raw
    def api(self,name,types,*args):
        if name=='cuModuleGetFunction':
            self.calls.append(name);key=args[2]
            if key not in self.functions:self.functions[key]=len(self.functions)+1
            C.cast(args[0],C.POINTER(C.c_void_p))[0]=self.functions[key];return
        if name=='cuMemcpyDtoH_v2':
            self.calls.append(name);self.reads.append(args[2])
            C.memmove(args[0],self.read_bytes(args[1].value,args[2]),args[2]);return
        if name=='cuLaunchKernel' and args[0].value==self.functions.get(b'resident_guard_snapshot'):
            self.calls.append(name);params=args[9]
            kinds=(C.c_ulonglong,)*3+(C.c_uint,C.c_ulonglong,C.c_uint,C.c_uint)
            addresses,status,output,guards,generation,first,count=[C.cast(params[i],C.POINTER(t)).contents.value for i,t in enumerate(kinds)]
            pointers=struct.unpack('<'+'Q'*guards,self.read_bytes(addresses,guards*8))
            raw=self.read_bytes(status,8)+struct.pack('<QII',generation,first,count)+b''.join(self.read_bytes(p,16)for p in pointers)
            self.write_bytes(output,raw)
            if self.after_snapshot:self.after_snapshot()
            return
        super().api(name,types,*args)


class SnapshotTables(Tables):
    read=VirtualTables.read
    def __init__(self,device,p):
        super().__init__(device,p);self.buffers={}
        for side,rows in (('A',p.m),('B',p.n)):
            raw,u=device.guarded(rows*p.rank);praw,pointer=device.guarded(p.k*4)
            self.buffers[side]=(raw,u,praw,pointer,rows)
    def close(self):
        if not self.closed:
            for raw,u,praw,p,rows in self.buffers.values():self.device.release(raw);self.device.release(praw)
            self.closed=True


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=SnapshotDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=SnapshotResidentBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
        self.dispatch=self.backend.dispatch
    def tearDown(self):self.backend.close();self.session.close()
    def window(self):return self.backend(FastBatch(self.plan,0,5),1,self.gen[0])
    def test_one_read_per_miss_and_all_twenty_eight_guards_each_window(self):
        owned=tuple(p.value for p in self.device.allocations);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.window().total,0)
        self.assertEqual(self.dispatch.guard_count,28)
        self.assertEqual(self.device.calls.count('cuMemcpyDtoH_v2'),1)
        self.assertEqual(self.device.reads,[504])
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),3)
        self.assertEqual(self.device.calls.count('cuMemcpyHtoD_v2'),1)
        self.assertEqual(tuple(p.value for p in self.device.allocations),owned)
    def test_each_guard_rejects_before_cursor_or_candidate_credit(self):
        for index in range(28):
            if index:
                self.backend.close();self.tables=SnapshotTables(self.device,self.p)
                with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
                    self.backend=SnapshotResidentBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
                self.dispatch=self.backend.dispatch
            address=self.dispatch.guard_addresses[index]
            with self.subTest(index=index):
                self.device.write_bytes(address,bytes(1))
                with self.assertRaisesRegex(RuntimeError,'guard'):self.window()
                self.assertEqual(self.device.verified_tiles,0)
                self.device.write_bytes(address,b'\xa5')
    def test_stale_snapshot_identity_is_rejected(self):
        self.device.after_snapshot=lambda:self.device.write_bytes(self.dispatch.snapshot[1].value+8,bytes(16))
        with self.assertRaisesRegex(RuntimeError,'identity'):self.window()
    def test_malformed_status_is_rejected(self):
        self.device.after_snapshot=lambda:self.device.write_bytes(self.dispatch.snapshot[1].value,struct.pack('<2I',6,1))
        with self.assertRaisesRegex(ValueError,'count'):self.window()
    def test_complete_and_partial_queues_keep_independent_cpu_check(self):
        batch=FastBatch(self.plan,0,5)
        def queue(total,overflow):
            self.device.write_bytes(self.dispatch.status[1].value,struct.pack('<2I',total,overflow))
            self.device.write_bytes(self.dispatch.queue[1].value,struct.pack('<3I',0,self.gen[0],0)+bytes(32))
        with patch('tools.snapshot_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
            self.device.after_launch=lambda:queue(5,1)
            self.assertTrue(self.backend(batch,1,self.gen[0]).overflow);reference.assert_not_called()
            self.device.after_launch=lambda:queue(1,0)
            self.assertFalse(self.backend(batch,1,self.gen[0]).overflow);reference.assert_called_once()
        self.assertEqual(self.device.verified_tiles,1)
    def test_stale_after_scanner_drains_without_cursor_credit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True];launches=[0]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_snapshot_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0])
        def change():
            launches[0]+=1
            if launches[0]==2:current[0]=False
        self.device.after_launch=change
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed)
            self.assertFalse(search.backend.dispatch.pending);self.assertEqual(self.device.allocations,[])
        finally:search.close()
    def test_direct_variant_keeps_twenty_four_argument_scan_abi(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=SnapshotDirectBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
        self.device.calls.clear();self.device.reads.clear();self.assertEqual(self.window().total,0)
        self.assertEqual(len(self.backend.dispatch.arguments),24)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2);self.assertEqual(self.device.reads,[504])
    def test_actual_cpp_collector_byte_layout(self):
        with tempfile.TemporaryDirectory()as temp:
            folder=Path(temp);source=folder/'snapshot.cpp'
            source.write_text('#include "guard_snapshot.h"\nextern "C" unsigned char byte(const unsigned long long*a,const unsigned char*s,unsigned long long g,unsigned f,unsigned n,unsigned i){return pearl_snapshot_byte(a,s,g,f,n,i);}\n')
            subprocess.run(['g++','-O2','-shared','-fPIC','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'snapshot.so')],check=True)
            lib=C.CDLL(str(folder/'snapshot.so'));lib.byte.argtypes=[C.c_void_p,C.c_void_p,C.c_ulonglong,C.c_uint,C.c_uint,C.c_uint];lib.byte.restype=C.c_ubyte
            guards=[C.create_string_buffer(bytes((j*17+i)%256 for i in range(16)),16)for j in range(28)]
            addresses=(C.c_ulonglong*28)(*(C.addressof(x)for x in guards));status=struct.pack('<2I',67,1)
            generation=(1<<63)+123;first=8388608-4096;count=4096
            expected=status+struct.pack('<QII',generation,first,count)+b''.join(x.raw for x in guards)
            actual=bytes(lib.byte(addresses,status,generation,first,count,i)for i in range(len(expected)))
            self.assertEqual(actual,expected)


if __name__=='__main__':unittest.main()
