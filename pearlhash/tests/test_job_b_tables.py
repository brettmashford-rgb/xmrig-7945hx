"""Shared allocation lifetime, binding, failure cleanup and retained GPU protocol. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.job_b_tables import JobBTables,new_job_b_search
from tools.virtual_scan import VirtualTables
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_lean_scan import ResetDevice
from test_prepared_dispatch import profile

class Device(ResetDevice):
    def __init__(self):super().__init__();self.noise=[];self.fail_noise=False
    def launch(self,name,args,blocks,threads):
        if name in (b'noise_uniform_range',b'noise_permutation'):
            self.noise.append((name,args[0].value))
            if self.fail_noise:raise RuntimeError('injected table build failure')
        else:super().launch(name,args,blocks,threads)

class Tables(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32));self.device=Device()
        self.p=replace(profile(),m=160,n=192)
        self.context=SimpleNamespace(job=self.job,profile=self.p)
        self.owner=JobBTables(self.device,self.context,self.session.is_current)
    def tearDown(self):self.owner.close();self.session.close();self.assertEqual(self.device.allocations,[])
    def test_two_nonces_regenerate_only_A_and_keep_B_pointers(self):
        pointers=tuple(p.value for p in self.owner.owned)
        for i in range(2):
            p=replace(self.p,seed_a=bytes([i+1])*32,tail=bytes([i+1])*16)
            tables=VirtualTables(self.device,p,b_cache=self.owner)
            self.assertIs(tables.buffers['B'],self.owner.buffer)
            self.assertEqual(tables.key_b.value,self.owner.key_b.value)
            tables.close();tables.close()
            self.assertEqual(tuple(p.value for p in self.device.allocations),pointers)
        self.assertEqual(len(self.device.noise),6);self.assertEqual(self.owner.leases,2)
    def test_busy_foreign_profile_device_and_closed_leases_reject(self):
        for p in (replace(self.p,seed_b=b'X'*32),replace(self.p,n=224),replace(self.p,k=65536)):
            with self.assertRaises(ValueError):VirtualTables(self.device,p,b_cache=self.owner)
        other=Device()
        with self.assertRaises(ValueError):VirtualTables(other,self.p,b_cache=self.owner)
        self.assertEqual(other.allocations,[])
        tables=VirtualTables(self.device,self.p,b_cache=self.owner)
        try:
            with self.assertRaises(ValueError):VirtualTables(self.device,self.p,b_cache=self.owner)
            with self.assertRaisesRegex(ValueError,'leased'):self.owner.close()
        finally:tables.close()
        self.owner.close()
        with self.assertRaises(ValueError):VirtualTables(self.device,self.p,b_cache=self.owner)
    def test_partial_A_failure_releases_lease_without_freeing_B(self):
        retained=tuple(self.device.allocations);self.device.fail_noise=True
        with self.assertRaisesRegex(RuntimeError,'injected'):VirtualTables(self.device,self.p,b_cache=self.owner)
        self.device.fail_noise=False
        self.assertFalse(self.owner.leased);self.assertEqual(tuple(self.device.allocations),retained)
    def test_owner_build_failure_and_stale_after_build_free_everything(self):
        other=Device();other.fail_noise=True
        with self.assertRaises(RuntimeError):JobBTables(other,self.context,self.session.is_current)
        self.assertEqual(other.allocations,[])
        other.fail_noise=False;calls=[0]
        def current(job):calls[0]+=1;return calls[0]==1
        with self.assertRaises(StaleWork):JobBTables(other,self.context,current)
        self.assertEqual(other.allocations,[])
    def test_guards_reject_before_new_lease(self):
        for pointer in (self.owner.buffer[0],self.owner.buffer[2]):
            self.device.write_bytes(pointer.value,b'\0')
            with self.assertRaisesRegex(RuntimeError,'guard'):VirtualTables(self.device,self.p,b_cache=self.owner)
            self.assertFalse(self.owner.leased)
            self.device.write_bytes(pointer.value,b'\xa5')
    def test_all_28_guard_faults_close_nonce_without_freeing_shared_B(self):
        retained=tuple(self.device.allocations)
        for index in range(28):
            search=new_job_b_search(self.context,self.device,self.session.is_current,self.owner)
            dispatch=search.backend.dispatch;address=dispatch.guard_addresses[index]
            self.device.write_bytes(address,bytes(16))
            with self.assertRaisesRegex(RuntimeError,'guard'):search.advance(1)
            self.assertTrue(search.closed);self.assertFalse(self.owner.leased)
            self.assertEqual(tuple(self.device.allocations),retained)
            raw,u,praw,perm,rows=self.owner.buffer
            if address in (raw.value,raw.value+rows*self.p.rank+16,praw.value,praw.value+self.p.k*4+16):
                self.device.write_bytes(address,b'\xa5'*16)
            self.owner.check_guards()

    def test_context_job_key_stale_and_seed_binding(self):
        bad=SimpleNamespace(job=replace(self.job,job_key=b'Y'*32),profile=self.p)
        with self.assertRaises(ValueError):self.owner.validate_context(bad,lambda job:True)
        with self.assertRaises(StaleWork):self.owner.validate_context(self.context,lambda job:False)
    def test_actual_search_cleanup_keeps_B_and_checks_28_guards_each_window(self):
        retained=tuple(self.device.allocations)
        with new_job_b_search(self.context,self.device,self.session.is_current,self.owner)as search:
            self.device.calls.clear();self.device.reads.clear()
            for size in (5,7):
                hit,cursor=search.advance(size);self.assertIsNone(hit)
            self.assertEqual(cursor.next_tile,12);self.assertEqual(search.backend.dispatch.guard_count,28)
            self.assertEqual(self.device.reads,[504,504])
            self.assertEqual(self.device.calls.count('cuLaunchKernel'),4)
            self.assertNotIn('cuCtxSynchronize',self.device.calls)
            self.session.consume(self.message)
            with self.assertRaises(StaleWork):search.advance(1)
            self.assertFalse(self.owner.leased)
        self.assertEqual(tuple(self.device.allocations),retained)

if __name__=='__main__':unittest.main()
