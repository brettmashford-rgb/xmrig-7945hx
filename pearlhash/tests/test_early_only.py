"""Early operands alone preserve original iteration and transcript boundaries and the validated lean ABI. ISC."""
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
from tools.early_only_scan import EarlyOnlyBackend,new_early_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class LoopContract(unittest.TestCase):
    def test_ptx_entry_keeps_24_slots_and_no_block_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.56-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',raw)
        for name in ('b_quad_early_only_scan',):
            part=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
            self.assertEqual(part.count('mma.sync'),2)
    def test_invalid_variant_rejected_before_any_job_or_device_work(self):
        for value in (0,1,'early',5,6.0,None):
            with self.assertRaises(ValueError):new_early_search(None,None,None,early=value)
    def test_hash_target_and_queue_tail_remain_verbatim_quad5(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/early_only_scan.cu').read_text()
        tail='    unsigned words[16];'
        self.assertEqual(old.split(tail,1)[1].split('\nextern "C"',1)[0].rstrip(),
                         new.split(tail,1)[1].split('\n#undef',1)[0].rstrip())
    def test_original_loop_with_single_safe_lookahead(self):
        current=0;used=[];loads=[0];folds=[]
        for offset in range(0,32768,32):
            self.assertEqual(current,offset)
            if offset+32<32768:next_value=offset+32;loads.append(next_value)
            used.append(current)
            if (offset+32)%128==0:folds.append((offset+32,((offset+32)//128-1)%16))
            if offset+32<32768:current=next_value
        self.assertEqual(used,list(range(0,32768,32)));self.assertEqual(loads,used)
        self.assertEqual(max(loads)+31,32767);self.assertEqual(len(folds),256)
        source=(ROOT/'gpu/early_only_scan.cu').read_text()
        self.assertIn('#pragma unroll 1',source)
        self.assertIn('for(unsigned offset=0;offset<32768;offset+=32)',source)
        self.assertNotIn('base+=128',source);self.assertNotIn('step<4',source)
    def test_original_transcript_fold_remains_verbatim(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/early_only_scan.cu').read_text()
        marker='        if((offset+32)%128==0)'
        old=old.split(marker,1)[1].split('    }\n    unsigned words[16];',1)[0]
        new=new.split(marker,1)[1].split('        if(offset+32<32768)current=next;',1)[0]
        self.assertEqual(old,new)


class EarlyOnly(unittest.TestCase):
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        backend=EarlyOnlyBackend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=backend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_entry_and_24_slot_abi_keep_exact_lean_driver_path(self):
        dispatch=self.backend.dispatch;entry=b'b_quad_early_only_scan'
        self.assertEqual(dispatch.function.value,self.device.functions[entry]);self.assertEqual(len(dispatch.arguments),24)
        self.assertEqual(dispatch.guard_count,28);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.backend(FastBatch(self.plan,0,5),1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2);self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1)
        self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
        self.assertEqual(self.device.reads,[504])
    def test_control_selector_uses_actual_quad5_entry(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            with new_early_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:True,early=False)as search:
                self.assertEqual(search.backend.dispatch.function.value,self.device.functions[b'b_quad_padded_scan'])
                hit,cursor=search.advance(5)
                self.assertIsNone(hit);self.assertEqual(cursor.next_tile,5)
    def test_stale_before_launch_rejects_without_gpu_work(self):
        self.gen[0]+=1;self.device.calls.clear()
        with self.assertRaisesRegex(ValueError,'stale'):self.backend(FastBatch(self.plan,0,5),1,self.job.generation)
        self.assertNotIn('cuLaunchKernel',self.device.calls)
    def test_search_generation_change_drains_without_cursor_credit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_early_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0])
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()



if __name__=='__main__':unittest.main()
