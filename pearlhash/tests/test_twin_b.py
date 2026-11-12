"""Actual two-nonce dispatch bindings, immutable sharing, cancellation and faults. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import re,struct,unittest
from unittest.mock import patch
from pool.search import prepare_base,StaleWork
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.check_prepared_job import synthetic_session
from tools.twin_b_scan import Twin,JobInputs,MODES,validate_pair
from test_job_b_tables import Device

ROOT=Path(__file__).resolve().parents[1]

class Twins(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32))
        base=prepare_base(self.job,self.session.is_current);front=NonceCommitmentCache.build(self.job,self.session.is_current)
        self.contexts=tuple(prepare_cached_nonce(self.job,base,b'TESTWORK',bytes([i])*8,self.session.is_current,front)for i in (1,2))
        self.device=Device();self.inputs=JobInputs(self.device,self.contexts[0],self.session.is_current);self.twins=[]
    def pair(self):
        t=Twin(self.contexts,self.device,self.session.is_current,self.inputs);self.twins.append(t);return t
    def tearDown(self):
        self.device.after_launch=None;self.device.after_reset=None
        for t in self.twins:t.close()
        self.inputs.close();self.session.close();self.assertFalse(self.device.allocations)
    def test_same_B_maps_distinct_A_keys_and_safe_partial_close(self):
        t=self.pair();a,b=t.dispatches
        self.assertEqual(len(t.arguments),29)
        for index in (1,3,5,20):self.assertEqual(a.arguments[index].value,b.arguments[index].value)
        for index in (0,7,8,9,10):self.assertNotEqual(a.arguments[index].value,b.arguments[index].value)
        self.assertEqual((self.inputs.b_pool.users,self.inputs.geometry_pool.users),(2,2))
        t.searches[0].close();self.assertTrue(self.inputs.b.leased);self.assertTrue(self.inputs.geometry.leased)
        with self.assertRaisesRegex(ValueError,'leased'):self.inputs.close()
        t.close();self.assertFalse(self.inputs.b.leased);self.assertFalse(self.inputs.geometry.leased)
    def test_full_window_fused_readback_driver_contract_and_retained_buffers(self):
        t=self.pair();retained=tuple(self.device.allocations)
        for mode in MODES:
            self.device.calls.clear();self.device.reads.clear()
            self.assertEqual(tuple(r.total for r in t.scan(mode,5,7)),(0,0))
            self.assertEqual(self.device.reads,[504,504])
            self.assertEqual(self.device.calls.count('cuLaunchKernel'),4 if mode=='pair-direct'else 3)
            self.assertEqual(self.device.calls.count('cuMemsetD32Async'),2)
            self.assertEqual(self.device.calls.count('cuStreamSynchronize'),2 if mode=='pair-direct'else 1)
            self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
            self.assertEqual(tuple(self.device.allocations),retained)
    def emit(self,t,total,wrong_lane=None):
        for lane,d in enumerate(t.dispatches):
            if d.loaded is None:continue
            cap=d.queue_capacity.value;gen=d.generation.value
            self.device.write_bytes(d.status[1].value,struct.pack('<2I',total,int(total>cap)))
            digest=bytes([1 if lane==wrong_lane else 0])+bytes(31)
            self.device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,gen&0xffffffff,gen>>32)+digest for i in range(min(total,cap))))
    def test_independent_full_queue_retry_and_CPU_verification_for_each_nonce(self):
        for mode in MODES:
            with self.pair()as t:
                self.device.after_launch=lambda:self.emit(t,17)
                with patch('tools.pair_depth_scan.global_reference',return_value=[(bytes(64),bytes(32))])as ref:
                    results=t.complete_scan(mode,0,17)
                self.assertEqual(tuple(len(r.records)for r in results),(17,17));self.assertEqual(t.retries,1)
                self.assertEqual(ref.call_count,34)
                self.assertEqual({id(call.args[0])for call in ref.call_args_list},{id(c.profile)for c in self.contexts})
                self.device.after_launch=None
    def test_second_nonce_wrong_digest_rejects_without_work_credit(self):
        t=self.pair();self.device.after_launch=lambda:self.emit(t,1,wrong_lane=1)
        with patch('tools.pair_depth_scan.global_reference',return_value=[(bytes(64),bytes(32))]):
            with self.assertRaisesRegex(ValueError,'CPU math'):t.complete_scan('twin-shared-b',0,1)
        self.assertTrue(t.closed);self.assertEqual(t.completed_unique_tiles,0)
    def test_both_domains_counted_once_and_no_credit_on_second_domain_failure(self):
        t=self.pair();t.run('twin-shared-b',0,35);self.assertEqual(t.completed_unique_tiles,70)
        self.device.after_snapshot=lambda:self.device.write_bytes(t.dispatches[1].snapshot[0].value,bytes(16))
        try:
            with self.assertRaisesRegex(RuntimeError,'guard'):t.run('twin-shared-b',35,40)
            self.assertEqual(t.completed_unique_tiles,70);self.assertTrue(t.closed)
        finally:self.device.after_snapshot=None
    def test_stale_after_reset_and_after_launch_drains_and_releases(self):
        for event in ('after_reset','after_launch'):
            with self.subTest(event=event):
                t=self.pair();current=[True];t.current=lambda job:current[0]
                setattr(self.device,event,lambda:current.__setitem__(0,False))
                with self.assertRaises(StaleWork):t.scan('twin-shared-b',0,1)
                setattr(self.device,event,None)
                self.assertTrue(t.closed);self.assertFalse(self.inputs.b.leased);self.assertFalse(self.inputs.geometry.leased)
                self.assertEqual(t.completed_unique_tiles,0)
    def test_stale_before_scan_closes_without_launch(self):
        t=self.pair();t.current=lambda job:False;self.device.calls.clear()
        with self.assertRaises(StaleWork):t.scan('twin-shared-b',0,1)
        self.assertNotIn('cuLaunchKernel',self.device.calls);self.assertTrue(t.closed)
    def test_all_56_guard_endpoints_reject_and_retained_inputs_survive(self):
        from tools.check_pair_depth import restore_retained_guard
        retained=tuple(self.device.allocations)
        for lane in (0,1):
            for index in range(28):
                t=self.pair();address=C.c_ulonglong(t.dispatches[lane].guard_addresses[index])
                self.device.write_bytes(address.value,bytes(16))
                with self.assertRaisesRegex(RuntimeError,'guard'):t.scan('twin-shared-b',0,1)
                restore_retained_guard(self.device,self.inputs.b,self.inputs.geometry,address)
                self.assertTrue(t.closed);self.assertEqual(tuple(self.device.allocations),retained)
    def test_second_A_construction_failure_releases_both_views_and_caches(self):
        from tools.resident_scan import CachedA
        calls=[0];retained=tuple(self.device.allocations)
        def build(tables):
            calls[0]+=1
            if calls[0]==2:raise RuntimeError('second cache failure')
            return CachedA(tables)
        with patch('tools.resident_scan.CachedA',side_effect=build):
            with self.assertRaisesRegex(RuntimeError,'second cache failure'):self.pair()
        self.assertFalse(self.inputs.b.leased);self.assertFalse(self.inputs.geometry.leased)
        self.assertEqual(tuple(self.device.allocations),retained)
    def test_wrong_job_B_binding_duplicate_nonce_and_aliases_reject(self):
        a,b=self.contexts
        for c in (a,replace(b,profile=replace(b.profile,seed_b=b'X'*32)),replace(b,job=replace(b.job,generation=999))):
            with self.assertRaises((ValueError,StaleWork)):validate_pair((a,c),self.session.is_current)
        with self.assertRaises(StaleWork):validate_pair(self.contexts,lambda j:False)
    def test_full_16K_overflow_count_for_both_nonces(self):
        from pool.session import MiningProfile
        with patch('tools.check_prepared_job.MiningProfile',side_effect=lambda m,n,k,r,rows,cols:MiningProfile(160,16384,k,r,rows,cols)):
            session,job,_=synthetic_session(bytes(32))
        inputs=None
        try:
            base=prepare_base(job,session.is_current);front=NonceCommitmentCache.build(job,session.is_current)
            contexts=tuple(prepare_cached_nonce(job,base,b'TESTWORK',bytes([i])*8,session.is_current,front)for i in(3,4))
            inputs=JobInputs(self.device,contexts[0],session.is_current)
            with Twin(contexts,self.device,session.is_current,inputs)as t:
                self.device.after_launch=lambda:self.emit(t,16384)
                results=t.scan('twin-shared-b',0,16384,capacity=0)
                self.assertTrue(all(r.total==16384 and r.overflow and not r.records for r in results))
                with patch('tools.pair_depth_scan.global_reference',return_value=[(bytes(64),bytes(32))])as ref:
                    results=t.complete_scan('twin-shared-b',0,16384)
                self.assertTrue(all(len(r.records)==16384 and not r.overflow for r in results))
                self.assertEqual(ref.call_count,32768);self.assertEqual(t.retries,1)
        finally:
            self.device.after_launch=None
            if inputs is not None:inputs.close()
            session.close()


class KernelContract(unittest.TestCase):
    def test_PTX_ABI_arithmetic_and_control_collector_unchanged(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.82-scan-sm120.ptx').read_text()
        old=(ROOT/'releases/pearlhash-dev-v0.0.80-scan-sm120.ptx').read_text()
        def entry(s,name):return s.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name,shared in (('twin_private_b_scan',14336),('twin_shared_b_scan',10240)):
            b=entry(raw,name);self.assertEqual(b.split(')')[0].count('.param '),29)
            self.assertEqual(b.count('mma.sync'),6);self.assertGreaterEqual(b.count('bar.sync'),3)
            self.assertEqual(sum(map(int,re.findall(r'\.shared \.align 4 \.b8 [^\n]+\[(\d+)\];',b))),shared)
        for name in ('a_pair_direct_scan','resident_guard_snapshot'):self.assertEqual(entry(raw,name),entry(old,name))
    def test_mma_fold_pointer_and_emit_body_unchanged(self):
        old=(ROOT/'gpu/a_share_scan.cu').read_text();new=(ROOT/'gpu/twin_b_scan.cu').read_text()
        start='        {\n            unsigned x0=ShareA?';end='extern "C" __global__'
        self.assertEqual(old.split(start,1)[1].split(end,1)[0],new.split(start,1)[1].split(end,1)[0])
        self.assertIn('if(!ReuseB||nonce==0U)',new)
        self.assertIn('if(nonce){ua=ua_second;key=key_second;status=status_second;candidates=candidates_second;audit_words=audit_second;}',new)
    def test_each_nonce_has_same_consumers_B_half_production_no_fragment_alias(self):
        for reuse in (False,True):
            writes={};consumers=set()
            for thread in range(512):
                nonce,local=divmod(thread,256);warp,lane=divmod(local,32)
                if not reuse or nonce==0:
                    side,step=divmod(warp,4)
                    for f in range(4):
                        index=(0 if reuse else nonce*1024)+((side*4+step)*4+f)*32+lane
                        self.assertNotIn(index,writes);writes[index]=(side,step,f,lane)
                for tile in range(4):consumers.add((nonce,warp%2,warp//2*4+tile,lane))
            self.assertEqual(len(writes),1024 if reuse else 2048);self.assertEqual(len(consumers),2048)
            for nonce in (0,1):
                for side in (0,1):
                    for step in range(4):
                        for f in range(4):
                            for lane in range(32):
                                i=(0 if reuse else nonce*1024)+((side*4+step)*4+f)*32+lane
                                self.assertEqual(writes[i],(side,step,f,lane))

if __name__=='__main__':unittest.main()
