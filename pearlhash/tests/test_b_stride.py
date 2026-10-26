"""New padding layouts preserve every B fragment and the validated lean ABI. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import random
import re
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_b_quad as quad_tests
from tools.b_stride_scan import BStride6Backend,BStride7Backend,new_b_stride_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class LayoutMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):quad_tests.PackedMath.setUpClass()
    @classmethod
    def tearDownClass(cls):quad_tests.PackedMath.tearDownClass()
    def test_every_lane_and_k_column_half_at_strides_six_and_seven(self):
        lib=quad_tests.PackedMath.lib;rng=random.Random(53053)
        signed=[rng.randrange(-128,128)for _ in range(128*16)]
        old=bytes((signed[index*16+row]&255)if row<16 else 0 for index in range(128)for row in range(18))
        pairs=tuple(rng.randrange(128)|(rng.randrange(128)<<16)for _ in range(32768));packed=struct.pack('<32768I',*pairs)
        for stride in (6,7):
            words=[sum((signed[index*16+block*4+byte]&255)<<(byte*8)for byte in range(4))if block<4 else 0
                for index in range(128)for block in range(stride)]
            cache=struct.pack('<'+'I'*len(words),*words)
            for offset in (0,32,96,128,16352,16384,32640,32736):
                for lane in range(32):
                    for high in (0,1):
                        for second in (0,1):
                            expected=lib.oldword(old,packed,lane//4+high*8,offset+(lane%4)*4+second*16)
                            self.assertEqual(lib.fragment(cache,packed,stride,offset,lane,high,second),expected)
    def test_ptx_both_entries_keep_24_slots_and_no_block_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.53-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',raw)
        for name in ('b_quad_stride6_scan','b_quad_stride7_scan'):
            part=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
    def test_invalid_stride_rejected_before_any_job_or_device_work(self):
        for value in (True,False,'6',4,8,6.0,None):
            with self.assertRaises(ValueError):new_b_stride_search(None,None,None,stride=value)


class Stride6(unittest.TestCase):
    stride=6
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        backend=BStride6Backend if self.stride==6 else BStride7Backend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=backend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_entry_and_24_slot_abi_keep_exact_lean_driver_path(self):
        dispatch=self.backend.dispatch;entry=('b_quad_stride'+str(self.stride)+'_scan').encode()
        self.assertEqual(dispatch.function.value,self.device.functions[entry]);self.assertEqual(len(dispatch.arguments),24)
        self.assertEqual(dispatch.guard_count,28);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.backend(FastBatch(self.plan,0,5),1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2);self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1)
        self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
        self.assertEqual(self.device.reads,[504])
    def test_stale_before_launch_rejects_without_gpu_work(self):
        self.gen[0]+=1;self.device.calls.clear()
        with self.assertRaisesRegex(ValueError,'stale'):self.backend(FastBatch(self.plan,0,5),1,self.job.generation)
        self.assertNotIn('cuLaunchKernel',self.device.calls)
    def test_search_generation_change_drains_without_cursor_credit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_b_stride_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0],stride=self.stride)
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()


class Stride7(Stride6):stride=7


if __name__=='__main__':unittest.main()
