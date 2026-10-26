"""Exact traversal coverage, canonical candidate IDs and retained shared-B lifecycle. ISC."""
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
from tools.shared_b_scan import (RowPairBackend,SharedBBackend,RowPairPrepared,RowPairQueries,
    new_shared_b_search,canonical_tile,traversal_ordinal,coverage_interval)
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class Mapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name);source=folder/'mapping.cpp'
        source.write_text('''#include "shared_b_axes.h"
#include <vector>
extern "C" unsigned tile(unsigned ordinal,unsigned columns){return shared_b_tile(ordinal,columns);}
extern "C" int exhaustive(unsigned rows,unsigned columns){
 unsigned count=rows*columns;std::vector<unsigned char> seen(count,0);
 for(unsigned i=0;i<count;++i){unsigned t=shared_b_tile(i,columns);
  if(t>=count||seen[t]++||shared_b_ordinal(t,columns)!=i)return 1;
  unsigned window=(i/65536)*65536;
  if(t<window||t>=window+65536)return 2;}
 for(auto value:seen)if(value!=1)return 3;return 0;}
''')
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
            '-shared','-fPIC','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'mapping.so')],check=True)
        cls.lib=C.CDLL(str(folder/'mapping.so'));cls.lib.exhaustive.argtypes=[C.c_uint,C.c_uint]
        cls.lib.tile.argtypes=[C.c_uint,C.c_uint];cls.lib.tile.restype=C.c_uint
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
    def tearDown(self):self.session.close()
    def test_cpp_all_8388608_ids_bijection_and_every_timed_work_set(self):
        self.assertEqual(self.lib.exhaustive(512,16384),0)
    def test_python_mapping_queries_and_inverse_match_actual_cpp(self):
        for ordinal in range(self.plan.count):
            tile=canonical_tile(self.plan,ordinal)
            self.assertEqual(tile,self.lib.tile(ordinal,len(self.plan.cols)))
            self.assertEqual(traversal_ordinal(self.plan,tile),ordinal)
        batch=FastBatch(self.plan,1,min(68,self.plan.count));queries=RowPairQueries(batch)
        for i in range(len(queries)):
            self.assertEqual(queries[i].rows,self.plan.indices(canonical_tile(self.plan,1+i))[0])
            self.assertEqual(queries[i].cols,self.plan.indices(canonical_tile(self.plan,1+i))[1])
        self.assertEqual(queries[-1],queries[len(queries)-1]);self.assertEqual(queries[:2],(queries[0],queries[1]))
    def test_whole_pair_intervals_have_identical_canonical_sets(self):
        width=2*len(self.plan.cols)
        for first in range(0,self.plan.count,width):
            self.assertEqual(coverage_interval(self.plan,first,first+width),(first,first+width))
            self.assertEqual(set(canonical_tile(self.plan,i)for i in range(first,first+width)),set(range(first,first+width)))
        for first,stop in ((1,width),(0,width-1),(0,0)):
            with self.assertRaises(ValueError):coverage_interval(self.plan,first,stop)
    def test_mapping_rejects_invalid_ordinals_and_odd_row_domains(self):
        for value in (True,-1,self.plan.count,1.0):
            with self.assertRaises(ValueError):canonical_tile(self.plan,value)
        odd=SimpleNamespace(rows=(1,),cols=(1,))
        with self.assertRaises(ValueError):canonical_tile(odd,0)
        for value in (0,1,None,'yes'):
            with self.assertRaises(ValueError):new_shared_b_search(None,None,None,shared=value)
    def test_ptx_both_entries_keep_24_slots_without_cta_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.60-scan-sm120.ptx').read_text()
        for entry in ('shared_b_order_control_scan','shared_b_pair_scan'):
            part=raw.split('.visible .entry '+entry+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
    def test_v59_reference_windows_reassemble_actual_canonical_queries(self):
        from tools.check_shared_b_job import canonical_window
        class Dispatch:
            def __init__(self):self.device=SimpleNamespace(last_transcripts=None);self.calls=[]
            def prepare_window(self,batch):return batch
            def scan_window(self,batch,prepared,generation,**kwargs):
                self.calls.append((batch.start,batch.stop))
                self.device.last_transcripts=tuple((tile,)*16 for tile in range(batch.start,batch.stop))
                return SimpleNamespace(total=0)
        for first,stop in ((0,24),(1,68),(self.plan.count-67,self.plan.count)):
            dispatch=Dispatch();batch=FastBatch(self.plan,first,stop)
            words=canonical_window(dispatch,self.plan,batch,1)
            self.assertEqual(words,tuple((canonical_tile(self.plan,i),)*16 for i in range(first,stop)))
            self.assertEqual(sum(b-a for a,b in dispatch.calls),stop-first)
    def test_mma_fold_and_emit_helpers_retain_v59_code(self):
        old=(ROOT/'gpu/transpose6_scan.cu').read_text();new=(ROOT/'gpu/shared_b_scan.cu').read_text()
        lines=lambda text:[line.strip()for line in text.strip().splitlines()]
        a='    unsigned a0=';b='        unsigned a0='
        original=old.split(b,1)[1].split('        if((offset+32)',1)[0]
        helper=new.split(a,1)[1].split('\n}',1)[0]
        self.assertEqual(lines(original),lines(helper))
        original=old.split('            unsigned folded=',1)[1].split('            unsigned slot=',1)[0]
        helper=new.split('    unsigned folded=',1)[1].split('    if(lane==slot)',1)[0]
        self.assertEqual(lines(original),lines(helper))
        original=old.split('    unsigned digest[8];',1)[1].split('\n}',1)[0]
        helper=new.split('    unsigned digest[8];',1)[1].split('\n}',1)[0]
        self.assertEqual(lines(original),lines(helper))
    def test_pair_odd_windows_never_omit_or_double_credit(self):
        for first in (0,1,31,32,33,self.plan.count-5):
            for count in (1,3,5):
                if first+count>self.plan.count:continue
                blocks=(count+(first&1)+15)//16;found=[]
                for warp in range(blocks*8):
                    ordinal=(first&~1)+warp*2
                    if ordinal>=first+count:continue
                    if ordinal>=first:found.append(ordinal)
                    if ordinal+1<first+count:found.append(ordinal+1)
                self.assertEqual(found,list(range(first,first+count)))


class Lifecycle(unittest.TestCase):
    shared=True
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.gen=[self.job.generation];self.create()
    def create(self):
        self.tables=SnapshotTables(self.device,self.p)
        backend=SharedBBackend if self.shared else RowPairBackend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=backend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_same_guards_reset_readback_and_odd_window_grid(self):
        d=self.backend.dispatch;self.assertEqual(len(d.arguments),24);self.assertEqual(d.guard_count,28)
        self.assertEqual(d.grid(4096,1),257 if self.shared else 512)
        owned=tuple(p.value for p in self.device.allocations);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.backend(FastBatch(self.plan,1,6),1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2)
        self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1);self.assertEqual(self.device.reads,[504])
        self.assertNotIn('cuCtxSynchronize',self.device.calls);self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls)
        self.assertEqual(tuple(p.value for p in self.device.allocations),owned)
    def test_foreign_row_major_preparation_is_rejected(self):
        from tools.lean_scan import UniformPrepared
        d=self.backend.dispatch;b=FastBatch(self.plan,1,6)
        with self.assertRaisesRegex(ValueError,'foreign'):
            d.scan_window(b,UniformPrepared(d.token,Queries(b),0),self.gen[0])
    def test_every_guard_still_rejects(self):
        for index in range(28):
            if index:self.backend.close();self.create()
            d=self.backend.dispatch;address=d.guard_addresses[index];self.device.write_bytes(address,bytes(16))
            try:
                with self.assertRaisesRegex(RuntimeError,'guard'):self.backend(FastBatch(self.plan,1,6),1,self.gen[0])
                self.assertEqual(self.device.verified_tiles,0)
            finally:self.device.write_bytes(address,b'\xa5'*16)
    def test_nonzero_traversal_hit_is_cpu_checked_and_returned_as_canonical(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_shared_b_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:True,shared=self.shared,start=1)
        d=search.backend.dispatch
        def hit():
            self.device.write_bytes(d.status[1].value,struct.pack('<2I',1,0))
            self.device.write_bytes(d.queue[1].value,struct.pack('<3I',0,self.job.generation,0)+bytes(32))
        self.device.after_launch=hit
        try:
            with patch('tools.lean_scan.global_reference',return_value=[(bytes(64),bytes(32))])as ref:
                found,cursor=search.advance(1)
                self.assertEqual(found.tile,len(self.plan.cols));self.assertEqual(cursor.next_tile,2)
                query=ref.call_args.args[1][0]
                self.assertEqual((query.rows,query.cols),self.plan.indices(found.tile))
                self.assertEqual(self.device.verified_tiles,1)
        finally:search.close()
    def test_overflow_retry_checks_complete_mapped_records_before_canonical_hit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_shared_b_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:True,shared=self.shared,start=1)
        d=search.backend.dispatch;capacities=[]
        def queue():
            capacity=d.queue_capacity.value;capacities.append(capacity)
            self.device.write_bytes(d.status[1].value,struct.pack('<2I',5,int(capacity<5)))
            raw=b''.join(struct.pack('<3I',i,self.job.generation,0)+bytes(32)for i in range(min(capacity,5)))
            self.device.write_bytes(d.queue[1].value,raw)
        self.device.after_launch=queue
        try:
            with patch('tools.lean_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
                found,cursor=search.advance(5)
                self.assertEqual(capacities,[1,5]);self.assertEqual(cursor.retries,1)
                self.assertEqual(cursor.next_tile,6);self.assertEqual(found.tile,canonical_tile(self.plan,1))
                self.assertEqual(reference.call_count,5);self.assertEqual(self.device.verified_tiles,5)
        finally:search.close()
    def test_stale_after_launch_drains_without_cursor_credit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_shared_b_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0],shared=self.shared,start=1)
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,1);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()
    def test_stale_after_reset_drains_without_scanner(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_shared_b_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0],shared=self.shared,start=1)
        self.device.after_reset=lambda:current.__setitem__(0,False);self.device.calls.clear()
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertNotIn('cuLaunchKernel',self.device.calls);self.assertEqual(search.cursor.next_tile,1)
            self.assertEqual(self.device.allocations,[])
        finally:search.close()


class OrderOnly(Lifecycle):shared=False


if __name__=='__main__':unittest.main()
