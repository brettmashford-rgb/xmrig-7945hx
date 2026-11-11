"""Combined packed-four geometry binding, ownership and canonical candidate lifecycle. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import patch
from pool.search import StaleWork
from tools.job_geometry import JobGeometry
from tools.eight_tile_scan import new_eight_search
from tools.eight_tile_scan import eight_canonical_tile
from tools.job_b_tables import JobBTables
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from test_job_b_tables import Device
from test_prepared_dispatch import profile

class Offset(unittest.TestCase):
    mode="eight-v069"
    maps=True
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32));self.device=Device()
        self.p=replace(profile(),m=160,n=192);self.context=SimpleNamespace(job=self.job,profile=self.p)
        self.b=JobBTables(self.device,self.context,self.session.is_current)
        self.owner=JobGeometry(self.device,self.job,self.session.is_current,maps=self.maps)
    def tearDown(self):
        self.owner.close();self.b.close();self.session.close();self.assertEqual(self.device.allocations,[])
    def search(self,context=None,start=0,current=None):
        return new_eight_search(context or self.context,self.device,current or self.session.is_current,self.b,self.owner,start=start,mode=self.mode)
    def restore(self,address):
        raw,u,praw,p,rows=self.b.buffer
        buffers=tuple(self.owner.axes)+((raw,u,rows*self.p.rank),(praw,p,self.p.k*4))
        if address in {a for raw,pointer,size in buffers for a in(raw.value,raw.value+size+16)}:
            self.device.write_bytes(address,b'\xa5'*16)
    def test_multiple_nonces_retain_plan_maps_but_refresh_A_and_queue_bindings(self):
        retained=tuple(self.device.allocations);axes=tuple(p.value for p in self.owner.owned)
        with patch.object(FastPlan,'from_job',side_effect=AssertionError('rebuilt plan')):
            for i in range(2):
                context=SimpleNamespace(job=self.job,profile=replace(self.p,seed_a=bytes([i+1])*32,tail=bytes([i+1])*16))
                with self.search(context,start=5)as search:
                    self.assertIs(search.plan,self.owner.plan);d=search.backend.dispatch
                    self.assertIs(search.backend.tables.profile,context.profile)
                    self.assertEqual(self.device.read_bytes(search.backend.tables.key_a.value,32),context.profile.seed_a)
                    self.assertEqual(self.device.read_bytes(search.backend.tables.tail.value,16),context.profile.tail)
                    self.assertEqual(self.device.read_bytes(d.targets[1].value,32),self.job.share_bound.to_bytes(32,'little'))
                    self.assertEqual(d.guard_count,28)
                    if self.maps:
                        self.assertEqual(tuple(v[0].value for v in d.axes),axes)
                        self.assertTrue(all(v[0]not in d.owned for v in d.axes))
                    self.device.calls.clear();self.device.reads.clear()
                    for amount in (5,7):
                        hit,cursor=search.advance(amount);self.assertIsNone(hit)
                    self.assertEqual(cursor.next_tile,17);self.assertEqual(self.device.reads,[504,504])
                    self.assertEqual(self.device.calls.count('cuLaunchKernel'),4)
                    self.assertEqual(self.device.calls.count('cuMemsetD32Async'),2)
                    self.assertNotIn('cuMemcpyHtoD_v2',self.device.calls);self.assertNotIn('cuCtxSynchronize',self.device.calls)
                self.assertFalse(self.owner.leased);self.assertEqual(tuple(self.device.allocations),retained)
        self.assertEqual(self.owner.leases,2)
    def test_all_guards_reject_and_release_nonce_only(self):
        retained=tuple(self.device.allocations)
        for i in range(28):
            search=self.search(start=5);address=search.backend.dispatch.guard_addresses[i]
            self.device.write_bytes(address,bytes(16))
            with self.assertRaisesRegex(RuntimeError,'guard'):search.advance(5)
            self.assertTrue(search.closed);self.assertEqual(search.cursor.next_tile,5)
            self.assertFalse(self.owner.leased);self.assertFalse(self.b.leased)
            self.assertEqual(tuple(self.device.allocations),retained);self.restore(address)
    def test_failed_A_or_dispatch_construction_releases_geometry_and_B(self):
        retained=tuple(self.device.allocations);self.device.fail_noise=True
        with self.assertRaisesRegex(RuntimeError,'injected'):self.search()
        self.device.fail_noise=False
        self.assertFalse(self.owner.leased);self.assertFalse(self.b.leased)
        self.assertEqual(tuple(self.device.allocations),retained)
        with patch('tools.resident_scan.CachedA',side_effect=RuntimeError('A cache failure')):
            with self.assertRaisesRegex(RuntimeError,'A cache failure'):self.search()
        self.assertFalse(self.owner.leased);self.assertFalse(self.b.leased)
        self.assertEqual(tuple(self.device.allocations),retained)
    def test_wrong_job_device_dimensions_patterns_and_closed_owner_reject(self):
        for job,p in ((replace(self.job,job_key=b'X'*32),self.p),
                (self.job,replace(self.p,m=161)),
                (replace(self.job,cert_version=2),self.p),
                (replace(self.job,profile=replace(self.job.profile,rows=self.job.profile.cols)),self.p)):
            with self.assertRaises(ValueError):self.owner.validate(SimpleNamespace(job=job,profile=p),self.device,lambda j:True)
        with self.assertRaises(ValueError):self.owner.validate(self.context,Device(),self.session.is_current)
        with self.assertRaises(StaleWork):self.owner.validate(self.context,self.device,lambda j:False)
        self.owner.close()
        with self.assertRaises(ValueError):self.search()
    def test_overlapping_leases_and_premature_owner_close_reject(self):
        with self.search()as search:
            with self.assertRaises(ValueError):self.search()
            with self.assertRaisesRegex(ValueError,'leased'):self.owner.close()
    def test_fresh_generation_refreshes_target_and_rejects_old_preparation(self):
        with self.search()as search:
            old=search.backend.dispatch.prepare_window(FastBatch(search.plan,0,1))
        self.message['result'][2]=(1).to_bytes(32,'little').hex();job=self.session.consume(self.message)
        context=SimpleNamespace(job=job,profile=self.p)
        with self.search(context)as search:
            d=search.backend.dispatch
            self.assertEqual(d.bound,job.share_bound);self.assertEqual(self.device.read_bytes(d.targets[1].value,32),job.share_bound.to_bytes(32,'little'))
            with self.assertRaisesRegex(ValueError,'foreign'):d.scan_window(FastBatch(search.plan,0,1),old,job.generation)
    def test_stale_reset_and_launch_drain_with_no_cursor_credit(self):
        retained=tuple(self.device.allocations)
        for hook in ('after_reset','after_launch'):
            valid=[True];search=self.search(start=5,current=lambda j:valid[0])
            setattr(self.device,hook,lambda:valid.__setitem__(0,False))
            with self.assertRaises(StaleWork):search.advance(5)
            setattr(self.device,hook,None)
            self.assertTrue(search.closed);self.assertEqual(search.cursor.next_tile,5)
            self.assertFalse(self.owner.leased);self.assertEqual(tuple(self.device.allocations),retained)
    def test_complete_overflow_retry_CPU_checks_canonical_hits(self):
        with self.search(start=5)as search:
            d=search.backend.dispatch;caps=[]
            def emit():
                cap=d.queue_capacity.value;caps.append(cap)
                self.device.write_bytes(d.status[1].value,struct.pack('<2I',5,int(cap<5)))
                self.device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,self.job.generation,0)+bytes(32)for i in range(min(cap,5))))
            self.device.after_launch=emit
            with patch('tools.lean_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
                hit,cursor=search.advance(5)
                self.assertEqual(hit.tile,eight_canonical_tile(search.plan,5));self.assertEqual(cursor.next_tile,10)
                self.assertEqual(caps,[1,5]);self.assertEqual(reference.call_count,5)
            self.device.after_launch=None
    def test_foreign_plan_cannot_borrow_maps(self):
        if self.maps:
            with self.search():
                with self.assertRaises(ValueError):self.owner.borrow_axes(self.device,FastPlan.from_job(self.job))


class Pointer(Offset):
    mode="eight-serial-v069"
