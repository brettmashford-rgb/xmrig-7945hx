"""Grouped/early loops preserve transcript boundaries and the validated lean ABI. ISC."""
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
from tools.b_loop_scan import BGroupedBackend,BEarlyBackend,new_b_loop_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class LoopContract(unittest.TestCase):
    def test_ptx_both_entries_keep_24_slots_and_no_block_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.55-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',raw)
        for name in ('b_quad_grouped_scan','b_quad_early_scan'):
            part=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
            self.assertEqual(part.count('mma.sync'),8)
    def test_invalid_variant_rejected_before_any_job_or_device_work(self):
        for value in (True,False,'6',5,6.0,None,'pipeline'):
            with self.assertRaises(ValueError):new_b_loop_search(None,None,None,variant=value)
    def test_hash_target_and_queue_tail_remain_verbatim_quad5(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/b_loop_scan.cu').read_text()
        tail='    unsigned words[16];'
        self.assertEqual(old.split(tail,1)[1].split('\nextern "C"',1)[0],
                         new.split(tail,1)[1].split('\nextern "C"',1)[0])
    def test_schedule_preserves_every_offset_and_transcript_boundary(self):
        baseline=list(range(0,32768,32))
        for early in (False,True):
            offsets=[];loads=[];folds=[]
            for base in range(0,32768,128):
                if early:loads.append(base)
                for step in range(4):
                    if early:
                        if step<3:loads.append(base+(step+1)*32)
                    else:loads.append(base+step*32)
                    offsets.append(base+step*32)
                folds.append((offsets[-1]+32,(base//128)%16))
            self.assertEqual(offsets,baseline);self.assertEqual(loads,baseline)
            self.assertEqual(folds,[(o+32,((o+32)//128-1)%16)for o in baseline if (o+32)%128==0])
            self.assertEqual(max(loads)+31,32767)
    def test_grouped_transcript_matches_sequential_wrapping_accumulators(self):
        # Signed tensor accumulations and transcript rotate/XOR use modulo 2^32.
        rng=random.Random(55055);mask=(1<<32)-1
        increments=[[rng.randrange(-(1<<30),1<<30)for _ in range(8)]for _ in range(1024)]
        def transcript(grouped):
            acc=[0]*8;words=[0]*16
            for base in range(0,1024,4 if grouped else 1):
                for step in range(4 if grouped else 1):
                    index=base+step;acc=[(a+b)&mask for a,b in zip(acc,increments[index])]
                if grouped or (base+1)%4==0:
                    end=base+4 if grouped else base+1;fold=0
                    for value in acc:fold^=value
                    slot=(end//4-1)%16;w=words[slot]
                    words[slot]=(((w<<13)|(w>>19))^fold)&mask
            return words
        self.assertEqual(transcript(False),transcript(True))


class Grouped(unittest.TestCase):
    variant='grouped'
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        backend=BGroupedBackend if self.variant=='grouped' else BEarlyBackend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=backend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_entry_and_24_slot_abi_keep_exact_lean_driver_path(self):
        dispatch=self.backend.dispatch;entry=('b_quad_'+('grouped'if self.variant=='grouped'else 'early')+'_scan').encode()
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
            search=new_b_loop_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0],variant=self.variant)
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()


class Early(Grouped):variant='early'


if __name__=='__main__':unittest.main()
