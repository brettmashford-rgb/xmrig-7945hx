"""Actual C++ quartet/slab helpers, exhaustive coverage and guarded lifecycle. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import random
import re
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pool.search import StaleWork
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import FastPlan,FastBatch
from tools.four_tile_scan import (FourBackend,PackedFourBackend,FourQueries,new_four_search,
    four_canonical_tile,four_traversal_ordinal,four_coverage_interval)
from tools.shared_b_scan import canonical_tile as pair_tile
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]

class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name)
        a_word=(ROOT/'gpu/four_tile_scan.cu').read_text().split('__device__ __forceinline__ unsigned four_a_word',1)[1].split('__device__ __forceinline__ void four_fold',1)[0]
        source='''#include "four_tile_axes.h"
#include "cached_a_pack.h"
#include <vector>
extern "C" int exhaustive(unsigned rows,unsigned columns){
 unsigned count=rows*columns;std::vector<unsigned char> seen(count,0);
 for(unsigned i=0;i<count;++i){unsigned t=four_tile_canonical(i,columns);
  if(t>=count||seen[t]++||four_tile_ordinal(t,columns)!=i)return 1;
  unsigned window=(i/65536)*65536;if(t<window||t>=window+65536)return 2;}
 for(auto v:seen)if(v!=1)return 3;return 0;}
extern "C" unsigned tile(unsigned i,unsigned c){return four_tile_canonical(i,c);}
extern "C" unsigned fold(unsigned slab,unsigned group,unsigned owner,unsigned low,unsigned high){return four_fold_value(slab,group,owner,low,high);}
'''
        source+='inline unsigned four_a_word'+a_word
        source+='extern "C" unsigned word(const signed char*a,const unsigned*r,unsigned b,unsigned row,unsigned k){return four_a_word(a,r,b,row,k);}\n'
        (folder/'check.cpp').write_text(source)
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-unknown-pragmas','-Wno-misleading-indentation',
            '-shared','-fPIC','-I'+str(ROOT/'gpu'),str(folder/'check.cpp'),'-o',str(folder/'check.so')],check=True)
        cls.lib=C.CDLL(str(folder/'check.so'));cls.lib.exhaustive.argtypes=[C.c_uint,C.c_uint]
        cls.lib.tile.argtypes=[C.c_uint,C.c_uint];cls.lib.tile.restype=C.c_uint
        cls.lib.fold.argtypes=[C.c_uint]*5;cls.lib.fold.restype=C.c_uint
        cls.lib.word.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint];cls.lib.word.restype=C.c_uint
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
    def tearDown(self):self.session.close()
    def test_all_8388608_ids_and_every_65536_tile_canonical_work_set(self):
        self.assertEqual(self.lib.exhaustive(512,16384),0)
    def test_python_queries_inverse_and_actual_Cpp_mapping(self):
        for ordinal in range(self.plan.count):
            tile=four_canonical_tile(self.plan,ordinal)
            self.assertEqual(tile,self.lib.tile(ordinal,len(self.plan.cols)))
            self.assertEqual(four_traversal_ordinal(self.plan,tile),ordinal)
        batch=FastBatch(self.plan,3,70);queries=FourQueries(batch)
        for i,q in enumerate(queries):self.assertEqual((q.rows,q.cols),self.plan.indices(four_canonical_tile(self.plan,3+i)))
        for first in range(0,self.plan.count,4*len(self.plan.cols)):
            stop=first+4*len(self.plan.cols);self.assertEqual(four_coverage_interval(self.plan,first,stop),(first,stop))
            self.assertEqual({four_canonical_tile(self.plan,i)for i in range(first,stop)},set(range(first,stop)))
    def test_actual_A_loader_keeps_all_40_canonical_rows_and_zeroes_8_padding_rows(self):
        raw=C.create_string_buffer(160*32768);offsets=(0,4,128,32764)
        for row in range(160):
            for offset in offsets:C.memmove(C.addressof(raw)+row*32768+offset,struct.pack('<I',(row*0x9e3779b9^offset*7)&0xffffffff),4)
        axes=b''.join(a.packed for a in self.plan.rows)
        for base in range(0,len(self.plan.rows),4):
            for position in range(48):
                for offset in offsets:
                    actual=self.lib.word(raw,axes,base,position,offset)
                    expected=0 if position>=40 else (self.plan.rows[base+position//10].indices[position%10]*0x9e3779b9^offset*7)&0xffffffff
                    self.assertEqual(actual,expected)
    def test_actual_fold_helper_preserves_each_tile_and_excludes_padding(self):
        rng=random.Random(64)
        for _ in range(256):
            expected=[0]*4;actual=[0]*4
            for slab in range(3):
                for group in range(8):
                    low,high=rng.getrandbits(32),rng.getrandbits(32)
                    for position,value in ((slab*16+group,low),(slab*16+group+8,high)):
                        if position<40:expected[position//10]^=value
                    for owner in range(4):actual[owner]^=self.lib.fold(slab,group,owner,low,high)
            self.assertEqual(actual,expected)
    def test_partial_quartet_windows_cover_each_query_exactly_once(self):
        for first in (0,1,2,3,31,32,33,self.plan.count-7):
            for count in (1,3,5,7):
                if first+count>self.plan.count:continue
                found=[]
                for warp in range(((count+(first&3)+31)//32)*8):
                    ordinal=(first&~3)+warp*4
                    for i in range(4):
                        if first<=ordinal+i<first+count:found.append(ordinal+i)
                self.assertEqual(found,list(range(first,first+count)))
    def test_quartet_reference_reassembles_actual_v060_pair_queries(self):
        from tools.check_four_tile_job import canonical_window
        class Dispatch:
            def __init__(self):self.device=SimpleNamespace(last_transcripts=None)
            def prepare_window(self,b):return b
            def scan_window(self,b,p,g,**kw):
                self.device.last_transcripts=tuple((pair_tile(b.plan,i),)*16 for i in range(b.start,b.stop))
                return SimpleNamespace(total=0)
        for first,stop in ((0,64),(3,70),(self.plan.count-67,self.plan.count)):
            b=FastBatch(self.plan,first,stop)
            self.assertEqual(canonical_window(Dispatch(),self.plan,b,1),tuple((four_canonical_tile(self.plan,i),)*16 for i in range(first,stop)))
    def test_invalid_ordinals_geometry_and_selectors_rejected(self):
        for value in (True,-1,self.plan.count,1.0):
            with self.assertRaises(ValueError):four_canonical_tile(self.plan,value)
        for value in (0,1,None,'yes'):
            with self.assertRaises(ValueError):new_four_search(None,None,None,packed=value)
        with self.assertRaises(ValueError):four_coverage_interval(self.plan,1,4*len(self.plan.cols))
        incompatible=replace(self.job,profile=replace(self.job.profile,m=74))
        device=ResetDevice()
        with self.assertRaisesRegex(ValueError,'multiple-of-four'):
            new_four_search(SimpleNamespace(job=incompatible,profile=replace(profile(),m=74,n=192)),device,lambda j:True)
        self.assertEqual(device.allocations,[])
    def test_both_ptx_entries_keep_24_slot_ABI_without_CTA_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.64-scan-sm120.ptx').read_text()
        for name,mmacount in (('four_tile_share_scan',8),('four_tile_packed_scan',6)):
            entry=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',entry.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',entry)
            self.assertEqual(entry.count('mma.sync.aligned.m16n8k32'),mmacount)
            self.assertNotIn('redux.sync',entry)

class Lifecycle(unittest.TestCase):
    packed=True
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32));self.p=replace(profile(),m=160,n=192)
        self.plan=FastPlan.from_job(self.job);self.device=ResetDevice();self.backend=None
    def tearDown(self):
        if self.backend is not None:self.backend.close()
        self.session.close();self.assertEqual(self.device.allocations,[])
    def make(self):
        tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=tables):
            self.backend=(PackedFourBackend if self.packed else FourBackend)(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.job.generation)
        return self.backend
    def search(self,start=3,current=None):
        tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=tables):
            search=new_four_search(SimpleNamespace(job=self.job,profile=self.p),self.device,current or self.session.is_current,packed=self.packed,start=start)
        self.backend=search.backend;return search
    def test_retained_partial_windows_keep_28_guards_and_driver_protocol(self):
        backend=self.make();d=backend.dispatch
        self.assertEqual(d.kernel_entry,b'four_tile_packed_scan'if self.packed else b'four_tile_share_scan')
        self.assertEqual(d.guard_count,28);self.assertEqual(d.grid(4096,3),129)
        owned=tuple(self.device.allocations);self.device.calls.clear();self.device.reads.clear()
        for first,stop in ((3,6),(6,13)):self.assertEqual(backend(FastBatch(self.plan,first,stop),1,self.job.generation).total,0)
        self.assertEqual(self.device.reads,[504,504]);self.assertEqual(self.device.calls.count('cuLaunchKernel'),4)
        self.assertEqual(self.device.calls.count('cuMemsetD32Async'),2)
        self.assertNotIn('cuCtxSynchronize',self.device.calls);self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls)
        self.assertEqual(tuple(self.device.allocations),owned)
    def test_each_of_28_guards_rejects_before_candidate_credit(self):
        for i in range(28):
            backend=self.make();self.device.write_bytes(backend.dispatch.guard_addresses[i],bytes(16))
            with self.assertRaisesRegex(RuntimeError,'guard'):backend(FastBatch(self.plan,3,6),1,self.job.generation)
            self.assertEqual(self.device.verified_tiles,0);backend.close()
    def test_complete_overflow_retry_CPU_checks_then_returns_canonical_hit(self):
        search=self.search();d=search.backend.dispatch;capacities=[]
        def emit():
            capacity=d.queue_capacity.value;capacities.append(capacity)
            self.device.write_bytes(d.status[1].value,struct.pack('<2I',5,int(capacity<5)))
            self.device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,self.job.generation,0)+bytes(32)for i in range(min(capacity,5))))
        self.device.after_launch=emit
        with patch('tools.lean_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
            hit,cursor=search.advance(5)
            self.assertEqual(hit.tile,four_canonical_tile(search.plan,3));self.assertEqual(cursor.next_tile,8)
            self.assertEqual(capacities,[1,5]);self.assertEqual(reference.call_count,5)
        search.close()
    def test_stale_after_reset_drains_without_launch_or_credit(self):
        valid=[True];search=self.search(current=lambda j:valid[0]);self.device.calls.clear()
        self.device.after_reset=lambda:valid.__setitem__(0,False)
        with self.assertRaises(StaleWork):search.advance(5)
        self.assertTrue(search.closed);self.assertEqual(search.cursor.next_tile,3);self.assertNotIn('cuLaunchKernel',self.device.calls)
    def test_stale_after_launch_drains_without_cursor_credit(self):
        valid=[True];search=self.search(current=lambda j:valid[0])
        self.device.after_launch=lambda:valid.__setitem__(0,False)
        with self.assertRaises(StaleWork):search.advance(5)
        self.assertTrue(search.closed);self.assertEqual(search.cursor.next_tile,3)

class ShareControl(Lifecycle):packed=False

if __name__=='__main__':unittest.main()
