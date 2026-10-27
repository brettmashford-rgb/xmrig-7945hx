"""Isolated fold substitution, readable PTX ABI, and unchanged dispatch lifecycle. ISC."""
from dataclasses import replace
from functools import reduce
from operator import xor
from pathlib import Path
import random
import re
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pool.search import StaleWork
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import FastPlan,FastBatch
from tools.redux_b_scan import ReduxBBackend,new_redux_b_search
from tools.shared_b_scan import canonical_tile
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]

class Source(unittest.TestCase):
    def test_entire_kernel_matches_control_except_fold_helper_name(self):
        original=(ROOT/'gpu/shared_b_scan.cu').read_text().split('extern "C" __global__ void shared_b_pair_scan(',1)[1].split('\n#undef PH_BQ_VALUES',1)[0]
        new=(ROOT/'gpu/redux_b_scan.cu').read_text().split('extern "C" __global__ void shared_b_redux_scan(',1)[1].split('\n#undef PH_BQ_ARGS',1)[0]
        self.assertEqual(original.strip(),new.replace('redux_b_fold(','shared_b_fold(').strip())
    def test_fold_has_one_exact_substitution_preserving_padding_rotate_and_slot(self):
        old=(ROOT/'gpu/shared_b_scan.cu').read_text().split('void shared_b_fold(',1)[1].split('__device__ __forceinline__ void shared_b_emit',1)[0]
        new=(ROOT/'gpu/redux_b_scan.cu').read_text().split('void redux_b_fold(',1)[1].split('extern "C" __global__',1)[0]
        expected=old.replace('for(unsigned delta=16;delta;delta>>=1)folded^=__shfl_xor_sync(0xffffffffU,folded,delta);',
            'asm volatile("redux.sync.xor.b32 %0, %1, 0xffffffff;" : "=r"(folded) : "r"(folded));')
        self.assertEqual(new.strip(),expected.strip())
    def test_warp_XOR_algebra_all_lanes_and_arbitrary_signed_accumulator_bits(self):
        rng=random.Random(63)
        vectors=[[0]*32,[0xffffffff]*32,*[[int(i==lane)<<bit for i in range(32)]for lane in range(32)for bit in (0,31)]]
        vectors.extend([[rng.getrandbits(32)for _ in range(32)]for _ in range(2000)])
        for values in vectors:
            expected=reduce(xor,values)
            for delta in (16,8,4,2,1):values=[v^values[i^delta]for i,v in enumerate(values)]
            self.assertEqual(values,[expected]*32)
    def test_ptx_contains_native_reductions_24_slots_and_unchanged_control(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.63-scan-sm120.ptx').read_text()
        entry=lambda name:raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
        new=entry('shared_b_redux_scan');old=entry('shared_b_pair_scan')
        self.assertEqual(len(re.findall(r'\.param\s+\.',new.split(')',1)[0])),24)
        self.assertEqual(new.count('redux.sync.xor.b32'),2);self.assertEqual(old.count('redux.sync.xor.b32'),0)
        self.assertEqual(old.count('shfl.sync')-new.count('shfl.sync'),10)
        self.assertNotIn('bar.sync',new)

class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32));self.p=replace(profile(),m=160,n=192)
        self.plan=FastPlan.from_job(self.job);self.device=ResetDevice();self.backend=None
    def tearDown(self):
        if self.backend is not None:self.backend.close()
        self.session.close();self.assertEqual(self.device.allocations,[])
    def make(self):
        tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=tables):
            self.backend=ReduxBBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.job.generation)
        return self.backend
    def test_native_dispatch_keeps_exact_window_driver_contract(self):
        backend=self.make();d=backend.dispatch
        self.assertEqual(d.kernel_entry,b'shared_b_redux_scan');self.assertEqual(d.guard_count,28)
        self.assertEqual(d.grid(4096,1),257)
        owned=tuple(self.device.allocations);self.device.calls.clear();self.device.reads.clear()
        for first,stop in ((1,6),(6,13)):self.assertEqual(backend(FastBatch(self.plan,first,stop),1,self.job.generation).total,0)
        self.assertEqual(self.device.reads,[504,504]);self.assertEqual(self.device.calls.count('cuLaunchKernel'),4)
        self.assertEqual(self.device.calls.count('cuMemsetD32Async'),2)
        self.assertNotIn('cuCtxSynchronize',self.device.calls);self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls)
        self.assertEqual(tuple(self.device.allocations),owned)
    def test_each_of_28_guards_rejects_before_candidate_credit(self):
        for i in range(28):
            backend=self.make();address=backend.dispatch.guard_addresses[i]
            self.device.write_bytes(address,bytes(16))
            with self.assertRaisesRegex(RuntimeError,'guard'):backend(FastBatch(self.plan,1,6),1,self.job.generation)
            self.assertEqual(self.device.verified_tiles,0);backend.close()
    def test_nonzero_hit_still_CPU_checked_and_remapped_to_canonical(self):
        tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=tables):
            search=new_redux_b_search(SimpleNamespace(job=self.job,profile=self.p),self.device,self.session.is_current,start=1)
        self.backend=search.backend;d=self.backend.dispatch
        def emit():
            self.device.write_bytes(d.status[1].value,struct.pack('<2I',1,0))
            self.device.write_bytes(d.queue[1].value,struct.pack('<3I',0,self.job.generation,0)+bytes(32))
        self.device.after_launch=emit
        with patch('tools.lean_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
            hit,cursor=search.advance(1)
            self.assertEqual(hit.tile,canonical_tile(search.plan,1));self.assertEqual(cursor.next_tile,2)
            self.assertEqual(reference.call_count,1);self.assertEqual(self.device.verified_tiles,1)
        search.close()
    def test_stale_after_reset_drains_and_does_not_launch_or_credit(self):
        tables=SnapshotTables(self.device,self.p);valid=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=tables):
            search=new_redux_b_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda j:valid[0],start=1)
        self.backend=search.backend;self.device.calls.clear()
        self.device.after_reset=lambda:valid.__setitem__(0,False)
        with self.assertRaises(StaleWork):search.advance(5)
        self.assertTrue(search.closed);self.assertEqual(search.cursor.next_tile,1)
        self.assertNotIn('cuLaunchKernel',self.device.calls)

if __name__=='__main__':unittest.main()
