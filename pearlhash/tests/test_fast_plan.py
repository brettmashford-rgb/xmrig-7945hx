"""Canonical global coverage, byte equality, lazy hits, retries and stale work. ISC."""
from dataclasses import replace
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.fast_plan import FastPlan,FastBatch,FastCandidateBackend,new_fast_search,Axis
from tools.check_prepared_job import synthetic_session
from tools.wide_scan import wide_plan_for,pack_wide
from tools.prepared_dispatch import QueryPacker
from tools.prepared_backend import PreparedCandidateBackend
from pool.search import StaleWork
from test_prepared_backend import Device,Tables
from test_prepared_dispatch import profile


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32))
        self.addCleanup(self.session.close)

    def test_all_small_domain_ids_maps_queries_and_bytes_match(self):
        old=wide_plan_for(self.job);fast=FastPlan.from_job(self.job)
        for i in range(old.count):self.assertEqual(old.indices(i),fast.indices(i))
        for start,stop in ((0,old.count),(1,99),(31,32),(0,0)):
            before=list(old.batches(start,stop));after=list(fast.batches(start,stop))
            self.assertEqual([(b.start,b.stop)for b in before],[(b.start,b.stop)for b in after])
            for a,b in zip(before,after):
                self.assertEqual(a.maps,tuple(b.maps));self.assertEqual(a.queries(),tuple(b.queries()))
                packed=fast.prepare(object(),b,7,4096)
                p=replace(profile(),m=160,n=192)
                self.assertEqual(packed.descriptors,pack_wide(p,a.queries()))
                self.assertEqual(packed.targets,(7).to_bytes(32,'little')*len(a.maps))

    def test_production_start_middle_end_cross_row_and_complete_interval_coverage(self):
        from pool.session import MiningProfile
        p=replace(self.job.profile,m=5121,n=262144)
        job=replace(self.job,profile=p);old=wide_plan_for(job);fast=FastPlan.from_job(job)
        self.assertEqual(fast.count,8388608)
        cursor=0
        for batch in fast.batches(0,fast.count):
            self.assertEqual(batch.start,cursor);cursor=batch.stop
        self.assertEqual(cursor,fast.count)
        rng=random.Random(38)
        for tile in [0,16383,16384,fast.count//2,fast.count-1]+[rng.randrange(fast.count)for _ in range(1000)]:
            self.assertEqual(fast.indices(tile),old.indices(tile))
        for first in (0,16380,fast.count//2,fast.count-4096):
            batch=next(fast.batches(first,first+4096));queries=tuple(batch.queries())
            self.assertEqual(fast.prepare(object(),batch,0,0).descriptors,pack_wide(profile(),queries))

    def test_forged_axes_bounds_shapes_profiles_and_foreign_batches_rejected(self):
        plan=FastPlan.from_job(self.job)
        for start,stop in ((-1,1),(True,2),(0,4097),(0,plan.count+1),(1,1)):
            with self.assertRaises(ValueError):FastBatch(plan,start,stop)
        with self.assertRaises(ValueError):replace(plan,prefixes=(bytes(136),)*len(plan.rows))
        with self.assertRaises(ValueError):replace(plan,prefixes=tuple(bytearray(p)for p in plan.prefixes))
        wrong=Axis(tuple(range(10)),bytes(128))
        with self.assertRaises(ValueError):replace(plan,rows=(wrong,)+plan.rows[1:])
        other=FastPlan.from_job(self.job);batch=next(other.batches(0,1))
        with self.assertRaises(ValueError):plan.prepare(object(),batch,0,0)
        with self.assertRaises(ValueError):FastPlan.from_job(replace(self.job,profile=replace(self.job.profile,k=4096)))

    def test_hits_and_queries_are_lazy_and_exactly_global(self):
        plan=FastPlan.from_job(self.job);batch=next(plan.batches(10,18))
        with patch('tools.fast_plan.TileQuery',side_effect=AssertionError('eager query construction')):
            prepared=plan.prepare(object(),batch,0,0)
            self.assertEqual(len(prepared.queries),8)
        self.assertEqual(prepared.queries[2].rows,plan.indices(12)[0])
        self.assertEqual(prepared.queries[-1].cols,plan.indices(17)[1])
        with self.assertRaises(IndexError):prepared.queries[8]

    def test_real_engine_reuses_buffers_and_rejects_replacement_during_launch(self):
        device=Device();context=SimpleNamespace(job=self.job,profile=replace(profile(),m=160,n=192))
        with patch('tools.prepared_backend.VirtualTables',Tables):
            search=new_fast_search(context,device,self.session.is_current)
            allocations=tuple(device.allocations)
            for end in (8,16):
                hit,cursor=search.advance(8);self.assertIsNone(hit);self.assertEqual(cursor.next_tile,end)
                self.assertEqual(tuple(device.allocations),allocations)
            device.after_launch=lambda:self.session.consume(self.message)
            with self.assertRaises(StaleWork):search.advance(8)
            self.assertEqual(cursor.next_tile,16);self.assertTrue(search.closed)
            self.assertEqual(device.allocations,[])

    def test_overflow_retry_prepares_once_and_cpu_checks_only_complete_returned_hits(self):
        import struct
        device=Device();context=SimpleNamespace(job=self.job,profile=replace(profile(),m=160,n=192))
        with patch('tools.prepared_backend.VirtualTables',Tables):
            search=new_fast_search(context,device,self.session.is_current,start=10)
            def launch():
                dispatch=search.backend.dispatch;capacity=dispatch.queue_capacity.value
                raw,off=device.locate(dispatch.status[1],0,8);raw[off:off+8]=struct.pack('<2I',2,int(capacity<2))
                for tile in range(min(2,capacity)):
                    raw,off=device.locate(dispatch.queue[1],tile*44,44)
                    raw[off:off+44]=struct.pack('<3I',tile,self.job.generation,0)+bytes(32)
            device.after_launch=launch
            with patch('tools.prepared_dispatch.global_reference',return_value=[(bytes(64),bytes(32))])as ref:
                hit,cursor=search.advance(8)
                self.assertEqual(ref.call_count,2)
            self.assertEqual((hit.tile,cursor.next_tile,cursor.retries),(10,18,1))
            self.assertEqual(search.backend.preparations,1);self.assertEqual(search.backend.dispatches,2)
            search.close();self.assertEqual(device.allocations,[])


if __name__=='__main__':unittest.main()
