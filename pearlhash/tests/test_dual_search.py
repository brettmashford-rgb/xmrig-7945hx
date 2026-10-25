"""Pair cursor atomicity, candidate IDs and stream resource ownership. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pool.search import NonceSearch,StaleWork
from tools.dual_search import DualBackend,DualSearch,intervals
from tools.fast_plan import FastPlan
from tools.check_prepared_job import synthetic_session
from test_cached_a import Device,Tables
from test_prepared_dispatch import profile
from tools.production_scan import ProductionCandidateScanner
from reference.tile_ranges import RangeCursor


class Backend(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32))
        self.plan=FastPlan.from_job(self.job);self.p=replace(profile(),m=160,n=192)
        self.device=Device();self.tables=Tables(self.device,self.p);self.generation=[self.job.generation]
        with patch('tools.dual_search.VirtualTables',return_value=self.tables):
            self.backend=DualBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.generation[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_pair_buffers_are_private_readonly_cache_shared_and_reused(self):
        before=tuple(p.value for p in self.device.allocations)
        self.assertEqual(self.backend.scan(0,5,self.job.generation),())
        self.assertEqual(self.backend.scan(5,12,self.job.generation),())
        self.assertEqual(tuple(p.value for p in self.device.allocations),before)
        self.assertEqual(self.backend.dispatches,4)
        self.assertEqual(self.backend.lanes[0].arguments[0].value,self.backend.lanes[1].arguments[0].value)
        self.assertNotEqual(self.backend.lanes[0].queue[1].value,self.backend.lanes[1].queue[1].value)
        self.backend.close();self.assertEqual(self.device.allocations,[])
    def test_replacement_between_launches_drains_first_and_releases_all(self):
        self.device.after_launch=lambda:self.generation.__setitem__(0,self.job.generation+1)
        with self.assertRaisesRegex(ValueError,'stale'):self.backend.scan(0,2,self.job.generation)
        self.assertTrue(self.backend.closed);self.assertFalse(any(l.pending for l in self.backend.lanes))
        self.assertEqual(self.device.allocations,[])
    def test_second_queue_failure_never_returns_first_candidate(self):
        with patch.object(self.backend.lanes[0],'finish',return_value=(SimpleNamespace(total=1,require_complete=lambda:{0:bytes(32)}),None)),\
             patch.object(self.backend.lanes[1],'finish',side_effect=RuntimeError('bad queue')):
            with self.assertRaisesRegex(RuntimeError,'bad queue'):self.backend.scan(0,2,self.job.generation)
        self.assertTrue(self.backend.closed);self.assertEqual(self.device.allocations,[])
    def test_global_ids_are_offset_and_sorted_across_lanes(self):
        result=lambda:SimpleNamespace(total=1,require_complete=lambda:{0:bytes(32)})
        with patch.object(self.backend.lanes[0],'finish',return_value=(result(),None)),\
             patch.object(self.backend.lanes[1],'finish',return_value=(result(),None)):
            self.assertEqual(self.backend.scan(5,12,self.job.generation),((5,bytes(32)),(9,bytes(32))))
    def test_single_final_tile_uses_only_one_lane(self):
        end=self.plan.count;self.backend.scan(end-1,end,self.job.generation)
        self.assertEqual(self.backend.dispatches,1)
    def test_bounds_and_generation_cannot_change(self):
        self.backend.scan(0,2,self.job.generation)
        with self.assertRaises(ValueError):self.backend.scan(0,2,self.job.generation+1)
        for a,b in ((0,8193),(-1,2),(0,0)):
            with self.assertRaises(ValueError):intervals(a,b)


class Cursor(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32));self.current=[True]
        self.search=DualSearch.__new__(DualSearch);self.search.closed=False;self.search.hit=None
        self.search.job=self.job;self.search.current=lambda job:self.current[0]
        self.search.plan=SimpleNamespace(count=20000);self.search.cursor=RangeCursor(self.job.generation,0,0)
        self.search.backend=SimpleNamespace(scan=lambda a,b,g:(),close=lambda:None)
    def tearDown(self):self.session.close()
    def test_window_credit_is_contiguous_including_final_tail(self):
        self.search.advance(8192);self.search.advance(8192);self.search.advance(8192)
        self.assertEqual(self.search.cursor.next_tile,20000);self.assertEqual(self.search.cursor.batches_done,6)
    def test_stale_pair_returns_no_cursor_credit_or_candidate(self):
        def scan(*args):self.current[0]=False;return ((0,bytes(32)),)
        self.search.backend.scan=scan
        with self.assertRaises(StaleWork):self.search.advance(8192)
        self.assertEqual(self.search.cursor.next_tile,0);self.assertIsNone(self.search.hit);self.assertTrue(self.search.closed)
    def test_pair_failure_keeps_previous_committed_window(self):
        self.search.advance(8192)
        self.search.backend.scan=lambda *args:(_ for _ in ()).throw(RuntimeError('GPU failed'))
        with self.assertRaises(RuntimeError):self.search.advance(8192)
        self.assertEqual(self.search.cursor.next_tile,8192);self.assertTrue(self.search.closed)
    def test_lowest_global_candidate_becomes_hit_after_complete_pair(self):
        self.search.backend.scan=lambda *args:((4096,bytes(32)),)
        hit,cursor=self.search.advance(8192)
        self.assertEqual(hit.tile,4096);self.assertEqual(cursor.next_tile,8192)
        with self.assertRaises(ValueError):self.search.advance(8192)


if __name__=='__main__':unittest.main()
