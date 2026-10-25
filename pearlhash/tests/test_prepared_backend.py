"""NonceSearch integration with reusable dispatches and a fake CUDA driver. ISC."""
from dataclasses import replace
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pool.search import NonceSearch,StaleWork
from tools.check_prepared_job import synthetic_session,backend_for
from tools.prepared_backend import PreparedCandidateBackend
from tools.production_scan import ProductionCandidateScanner
from tools.wide_scan import wide_plan_for,WideBatch
from test_prepared_dispatch import FakeDevice,FakeTables,profile


class Device(FakeDevice,ProductionCandidateScanner):pass


class Tables(FakeTables):
    def __init__(self,device,profile):
        super().__init__(device);self.profile=profile
    def close(self):self.closed=True


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.device=Device();self.session,self.job,self.message=synthetic_session(bytes(32))
        self.context=SimpleNamespace(job=self.job,profile=replace(profile(),m=160,n=192))
        self.patch=patch('tools.prepared_backend.VirtualTables',Tables);self.patch.start()
        self.addCleanup(self.patch.stop);self.addCleanup(self.session.close)

    def search(self,**kwargs):
        return NonceSearch(self.context,self.device,self.session.is_current,
            backend_factory=kwargs.get('backend_factory',backend_for(self.job,self.session.is_current)),
            plan_factory=wide_plan_for)

    def test_windows_keep_one_allocation_set_and_replacement_closes_it(self):
        search=self.search();backend=search.backend
        owned=tuple(self.device.allocations)
        for end in (8,16):
            hit,cursor=search.advance(8)
            self.assertIsNone(hit);self.assertEqual(cursor.next_tile,end)
            self.assertEqual(tuple(self.device.allocations),owned)
        self.assertEqual(backend.preparations,2);self.assertEqual(backend.dispatches,2)
        self.assertEqual(backend.stats()['dispatch_buffer_allocations'],5)
        self.session.consume(self.message)
        with self.assertRaises(StaleWork):search.advance(8)
        self.assertTrue(search.closed);self.assertTrue(backend.tables.closed)
        self.assertEqual(self.device.allocations,[])

    def test_overflow_retry_reuses_prepared_batch_and_preserves_global_tile(self):
        search=self.search();backend=search.backend
        def launch():
            dispatch=backend.dispatch;capacity=dispatch.queue_capacity.value
            data,off=self.device.locate(dispatch.status[1],0,8)
            data[off:off+8]=struct.pack('<2I',2,int(capacity<2))
            for tile in range(min(2,capacity)):
                raw=struct.pack('<3I',tile,self.job.generation,0)+bytes(32)
                data,off=self.device.locate(dispatch.queue[1],tile*44,44);data[off:off+44]=raw
        self.device.after_launch=launch
        with patch('tools.prepared_dispatch.global_reference',return_value=[(bytes(64),bytes(32))]):
            hit,cursor=search.advance(8)
        self.assertEqual((hit.tile,cursor.next_tile,cursor.retries),(0,8,1))
        self.assertEqual(backend.preparations,1);self.assertEqual(backend.dispatches,2)
        self.assertEqual(self.device.verified_tiles,2)
        self.assertEqual(backend.batch.maps,tuple(search.plan.indices(i)for i in range(8)))
        search.close();self.assertEqual(self.device.allocations,[])

    def test_replacement_during_launch_cannot_commit_or_credit_hits(self):
        search=self.search()
        self.device.after_launch=lambda:self.session.consume(self.message)
        with self.assertRaises(StaleWork):search.advance(8)
        self.assertEqual(search.cursor.next_tile,0)
        self.assertEqual(self.device.verified_tiles,0);self.assertTrue(search.closed)
        self.assertEqual(self.device.allocations,[])

    def test_backend_close_report_once_and_generation_cannot_change(self):
        reports=[]
        backend=PreparedCandidateBackend(self.context.profile,self.device,bound=0,on_close=reports.append)
        batch=next(wide_plan_for(self.job).batches(0,2));backend(batch,0,1<<63)
        with self.assertRaises(ValueError):backend(batch,0,(1<<63)+1)
        backend.close();backend.close()
        self.assertEqual(len(reports),1);self.assertTrue(reports[0]['closed'])
        self.assertEqual(reports[0]['prepared_batches'],1)
        self.assertEqual(self.device.allocations,[])


if __name__=='__main__':unittest.main()
