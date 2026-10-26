"""Biased six-bit production noise preserves B values and v57 lifecycle and the validated lean ABI. ISC."""
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
from tools.b_bias_scan import BBiasBackend,new_bias_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_snapshot_scan import SnapshotTables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class LoopContract(unittest.TestCase):
    def test_ptx_entry_keeps_24_slots_and_no_block_barriers(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.58-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',raw)
        for name in ('b_quad_biased_scan',):
            part=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(len(re.findall(r'\.param\s+\.',part.split(')',1)[0])),24)
            self.assertNotIn('bar.sync',part)
            self.assertEqual(part.count('mma.sync'),2)
    def test_invalid_variant_rejected_before_any_job_or_device_work(self):
        for value in (0,1,'early',5,6.0,None):
            with self.assertRaises(ValueError):new_bias_search(None,None,None,biased=value)
    def test_hash_target_and_queue_tail_remain_verbatim_quad5(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/b_bias_scan.cu').read_text()
        tail='    unsigned words[16];'
        self.assertEqual(old.split(tail,1)[1].split('\nextern "C"',1)[0].rstrip(),
                         new.split(tail,1)[1].split('\n#undef',1)[0].rstrip())
    def test_a_mma_transcript_and_final_tail_remain_verbatim(self):
        old=(ROOT/'gpu/b_quad_scan.cu').read_text();new=(ROOT/'gpu/b_bias_scan.cu').read_text()
        marker='        unsigned a0='
        old=old.split(marker,1)[1].split('\nextern "C"',1)[0].rstrip()
        new=new.split(marker,1)[1].split('\n#undef',1)[0].rstrip()
        self.assertEqual(old,new)
    def test_ptx_retains_v57_shuffle_count(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.58-scan-sm120.ptx').read_text()
        count=lambda name:raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].count('shfl.sync')
        self.assertEqual(count('b_quad_transpose_scan'),count('b_quad_biased_scan'))


class Biased(unittest.TestCase):
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.tables=SnapshotTables(self.device,self.p)
        self.gen=[self.job.generation]
        backend=BBiasBackend
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=backend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_entry_and_24_slot_abi_keep_exact_lean_driver_path(self):
        dispatch=self.backend.dispatch;entry=b'b_quad_biased_scan'
        self.assertEqual(dispatch.function.value,self.device.functions[entry]);self.assertEqual(len(dispatch.arguments),24)
        self.assertEqual(dispatch.guard_count,28);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.backend(FastBatch(self.plan,0,5),1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2);self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1)
        self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
        self.assertEqual(self.device.reads,[504])
    def test_control_selector_uses_actual_quad5_entry(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            with new_bias_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:True,biased=False)as search:
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
            search=new_bias_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0])
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed);self.assertEqual(self.device.allocations,[])
        finally:search.close()



class BiasedMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quad_tests.PackedMath.setUpClass()
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name)
        source=folder/'transpose.cpp'
        source.write_text('''#include "b_transpose.h"
#include "b_quad.h"
#include "b_bias.h"
extern "C" unsigned difference(unsigned a,unsigned b){return b_bias_difference(a,b);}
extern "C" unsigned bias(int value){return b_bias_byte(value);}
static unsigned permute(unsigned a,unsigned b,unsigned selector){
 unsigned out=0;for(unsigned byte=0;byte<4;++byte){unsigned from=(selector>>(byte*4))&7U;
 unsigned value=from<4?a:b;out|=((value>>((from&3U)*8))&255U)<<(byte*8);}return out;}
extern "C" void fragments(const unsigned*cache,const unsigned*pairs,unsigned offset,unsigned*out){
 for(unsigned high=0;high<2;++high)for(unsigned second=0;second<2;++second){
 unsigned values[32],next[32];
 for(unsigned lane=0;lane<32;++lane)values[lane]=b_bias_value(cache,pairs[offset+b_transpose_index(lane)+second*16],(lane>>4)+high*2);
 for(unsigned stage=0;stage<2;++stage){
 for(unsigned lane=0;lane<32;++lane)next[lane]=permute(values[lane],values[lane^(4U<<stage)],b_transpose_selector(lane,stage));
 for(unsigned lane=0;lane<32;++lane)values[lane]=next[lane];}
 for(unsigned lane=0;lane<32;++lane)out[(high*2+second)*32+lane]=values[lane];}}
''')
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'transpose.so')],check=True)
        cls.lib=C.CDLL(str(folder/'transpose.so'));cls.lib.fragments.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p]
        cls.lib.difference.argtypes=[C.c_uint,C.c_uint];cls.lib.difference.restype=C.c_uint
        cls.lib.bias.argtypes=[C.c_int];cls.lib.bias.restype=C.c_uint
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup();quad_tests.PackedMath.tearDownClass()
    def test_all_4096_production_byte_pairs_without_cross_byte_borrow(self):
        pack=lambda values:sum(v<<(8*i)for i,v in enumerate(values))
        for a in range(64):
            for b in range(64):
                aa=(a,63-a,a^21,a^42);bb=(b,b^21,63-b,b^42)
                self.assertEqual(self.lib.difference(pack(aa),pack(bb)),pack(tuple(64+x-y for x,y in zip(aa,bb))))
        for value in range(-32,32):self.assertEqual(self.lib.bias(value),value+32)
    def test_shared_cache_representation_has_canonical_noise_provenance(self):
        source=(ROOT/'gpu/virtual_tile_scan.cu').read_text()
        self.assertIn('int((hash[byte/4]>>(8*(byte%4)))&63U)-32',source)
        scan=(ROOT/'gpu/b_bias_scan.cu').read_text()
        self.assertIn('b_bias_byte(int(ub[cb[row]*128+index]))',scan)
        self.assertIn('rank!=128||fill!=64',scan)
    def test_every_lane_all_1024_offsets_both_halves_and_column_blocks(self):
        for seed in (57057,57058):
            rng=random.Random(seed);signed=[rng.randrange(-32,32)for _ in range(128*16)]
            old=bytes((signed[index*16+row]&255)if row<16 else 0 for index in range(128)for row in range(18))
            pairs=struct.pack('<32768I',*(rng.randrange(128)|(rng.randrange(128)<<16)for _ in range(32768)))
            words=[sum(((signed[index*16+block*4+byte]+32)&255)<<(byte*8)for byte in range(4))if block<4 else 0
                for index in range(128)for block in range(5)]
            cache=struct.pack('<640I',*words);output=(C.c_uint*128)()
            for offset in range(0,32768,32):
                self.lib.fragments(cache,pairs,offset,output)
                for high in (0,1):
                    for second in (0,1):
                        for lane in range(32):
                            expected=quad_tests.PackedMath.lib.oldword(old,pairs,lane//4+high*8,offset+(lane%4)*4+second*16)
                            self.assertEqual(output[(high*2+second)*32+lane],expected)


if __name__=='__main__':unittest.main()
