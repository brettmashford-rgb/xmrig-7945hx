"""Stride-six retest preserves v57 mapping and lifecycle and the validated lean ABI. ISC."""
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
import test_b_quad as quad_tests
from tools.transpose6_scan import Transpose6Backend,new_transpose6_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class LoopContract(unittest.TestCase):
    def test_ptx_entry_keeps_24_slots_and_no_block_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.59-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',raw)
        for name in ('b_quad_transpose6_scan',):
            part=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
            self.assertEqual(part.count('mma.sync'),2)
    def test_invalid_variant_rejected_before_any_job_or_device_work(self):
        for value in (0,1,'early',5,6.0,None):
            with self.assertRaises(ValueError):new_transpose6_search(None,None,None,padded=value)
    def test_hash_target_and_queue_tail_remain_verbatim_quad5(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/transpose6_scan.cu').read_text()
        tail='    unsigned words[16];'
        self.assertEqual(old.split(tail,1)[1].split('\nextern "C"',1)[0].rstrip(),
                         new.split(tail,1)[1].split('\n#undef',1)[0].rstrip())
    def test_a_mma_transcript_and_final_tail_remain_verbatim(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/transpose6_scan.cu').read_text()
        marker='        unsigned a0='
        old=old.split(marker,1)[1].split('\nextern "C"',1)[0].rstrip()
        new=new.split(marker,1)[1].split('\n#undef',1)[0].rstrip()
        self.assertEqual(old,new)
    def test_ptx_retains_v57_shuffle_count(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.59-scan-sm120.ptx').read_text()
        count=lambda name:raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].count('shfl.sync')
        self.assertEqual(count('b_quad_transpose_scan'),count('b_quad_transpose6_scan'))


class StrideSix(unittest.TestCase):
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        backend=Transpose6Backend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=backend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_entry_and_24_slot_abi_keep_exact_lean_driver_path(self):
        dispatch=self.backend.dispatch;entry=b'b_quad_transpose6_scan'
        self.assertEqual(dispatch.function.value,self.device.functions[entry]);self.assertEqual(len(dispatch.arguments),24)
        self.assertEqual(dispatch.guard_count,28);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.backend(FastBatch(self.plan,0,5),1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2);self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1)
        self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
        self.assertEqual(self.device.reads,[504])
    def test_control_selector_uses_actual_quad5_entry(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            with new_transpose6_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:True,padded=False)as search:
                self.assertEqual(search.backend.dispatch.function.value,self.device.functions[b'b_quad_transpose_scan'])
                hit,cursor=search.advance(5)
                self.assertIsNone(hit);self.assertEqual(cursor.next_tile,5)
    def test_stale_before_launch_rejects_without_gpu_work(self):
        self.gen[0]+=1;self.device.calls.clear()
        with self.assertRaisesRegex(ValueError,'stale'):self.backend(FastBatch(self.plan,0,5),1,self.job.generation)
        self.assertNotIn('cuLaunchKernel',self.device.calls)
    def test_search_generation_change_drains_without_cursor_credit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_transpose6_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0])
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()



class StrideSixMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quad_tests.PackedMath.setUpClass()
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name)
        source=folder/'transpose.cpp'
        source.write_text('''#include "b_transpose.h"
#include "b_quad.h"
static unsigned permute(unsigned a,unsigned b,unsigned selector){
 unsigned out=0;for(unsigned byte=0;byte<4;++byte){unsigned from=(selector>>(byte*4))&7U;
 unsigned value=from<4?a:b;out|=((value>>((from&3U)*8))&255U)<<(byte*8);}return out;}
extern "C" void fragments(const unsigned*cache,const unsigned*pairs,unsigned offset,unsigned*out){
 for(unsigned high=0;high<2;++high)for(unsigned second=0;second<2;++second){
 unsigned values[32],next[32];
 for(unsigned lane=0;lane<32;++lane)values[lane]=b_quad_value(cache,6,pairs[offset+b_transpose_index(lane)+second*16],(lane>>4)+high*2);
 for(unsigned stage=0;stage<2;++stage){
 for(unsigned lane=0;lane<32;++lane)next[lane]=permute(values[lane],values[lane^(4U<<stage)],b_transpose_selector(lane,stage));
 for(unsigned lane=0;lane<32;++lane)values[lane]=next[lane];}
 for(unsigned lane=0;lane<32;++lane)out[(high*2+second)*32+lane]=values[lane];}}
''')
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'transpose.so')],check=True)
        cls.lib=C.CDLL(str(folder/'transpose.so'));cls.lib.fragments.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup();quad_tests.PackedMath.tearDownClass()
    def test_every_lane_all_1024_offsets_both_halves_and_column_blocks(self):
        for seed in (57057,57058):
            rng=random.Random(seed);signed=[rng.randrange(-128,128)for _ in range(128*16)]
            old=bytes((signed[index*16+row]&255)if row<16 else 0 for index in range(128)for row in range(18))
            pairs=struct.pack('<32768I',*(rng.randrange(128)|(rng.randrange(128)<<16)for _ in range(32768)))
            words=[sum((signed[index*16+block*4+byte]&255)<<(byte*8)for byte in range(4))if block<4 else 0
                for index in range(128)for block in range(6)]
            cache=struct.pack('<768I',*words);output=(C.c_uint*128)()
            for offset in range(0,32768,32):
                self.lib.fragments(cache,pairs,offset,output)
                for high in (0,1):
                    for second in (0,1):
                        for lane in range(32):
                            expected=quad_tests.PackedMath.lib.oldword(old,pairs,lane//4+high*8,offset+(lane%4)*4+second*16)
                            self.assertEqual(output[(high*2+second)*32+lane],expected)


if __name__=='__main__':unittest.main()
