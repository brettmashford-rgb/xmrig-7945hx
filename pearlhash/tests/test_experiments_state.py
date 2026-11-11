"""Panel lifetime/parameter binding and large complete queue retries. ISC."""
import ctypes as C
from dataclasses import replace
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import patch
from tools.experiments_scan import new_search,Batch,decode,validate,MODES
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import FastPlan
from tools.job_geometry import JobGeometry
from tools.job_b_tables import JobBTables
from test_prepared_dispatch import profile
from test_job_b_tables import Device

class State(unittest.TestCase):
    def setUp(self):
        self.session,self.job,self.message=synthetic_session(bytes(32));self.device=Device();self.p=replace(profile(),m=160,n=192)
        self.context=SimpleNamespace(job=self.job,profile=self.p);self.b=JobBTables(self.device,self.context,self.session.is_current)
        self.g=JobGeometry(self.device,self.job,self.session.is_current,maps=True)
    def tearDown(self):self.g.close();self.b.close();self.session.close();self.assertEqual(self.device.allocations,[])
    def search(self,mode):return new_search(self.context,self.device,self.session.is_current,self.b,self.g,mode=mode)
    def test_superseded_preparation_rejects_for_every_mode(self):
        for mode in MODES:
            with self.search(mode)as search:
                d=search.backend.dispatch;a=Batch(search.plan,0,1);old=d.prepare_window(a)
                b=Batch(search.plan,1,2);d.prepare_window(b)
                with self.assertRaisesRegex(ValueError,'foreign'):d.scan_window(a,old,self.job.generation)
    def test_panel_cache_reused_and_included_in_snapshot(self):
        with self.search('panel')as search:
            d=search.backend.dispatch
            self.device.after_launch=lambda:self.device.write_bytes(d.panel_buffer[1].value,struct.pack('<12I',*([1]*12)))
            d.prepare_window(Batch(search.plan,0,1));self.assertEqual(d.panel_builds,1)
            d.prepare_window(Batch(search.plan,1,2));self.assertEqual(d.panel_builds,1)
            self.assertEqual(d.guard_count,30);self.assertIn(d.panel_buffer[0].value,d.covered)
            self.assertEqual(d.arguments[1].value,d.panel_buffer[1].value)
            self.assertIsNot(d.arguments[-1],d.first)
            self.device.after_launch=None
    def test_invalid_panel_flags_do_not_mark_cache_ready(self):
        with self.search('panel')as search:
            d=search.backend.dispatch;d.prepare_window(Batch(search.plan,0,1))
            self.assertIsNone(d.panel_ready);d.prepare_window(Batch(search.plan,1,2));self.assertEqual(d.panel_builds,2)
    def test_both_extra_panel_guards_are_detected(self):
        for index in (28,29):
            with self.search('panel-control')as search:
                d=search.backend.dispatch;self.device.write_bytes(d.guard_addresses[index],bytes(16))
                with self.assertRaisesRegex(RuntimeError,'guard'):search.advance(1)
    def test_panel_materialization_stale_launch_drains_and_closes(self):
        valid=[True];search=new_search(self.context,self.device,lambda job:valid[0],self.b,self.g,mode='panel')
        self.device.after_launch=lambda:valid.__setitem__(0,False)
        with self.assertRaises(Exception):search.advance(1)
        self.device.after_launch=None;self.assertTrue(search.closed);self.assertEqual(search.cursor.next_tile,0)
        self.assertFalse(self.g.leased);self.assertFalse(self.b.leased)
    def test_wide_allocation_sizes_are_grown_before_snapshot(self):
        with self.search('wide16k')as search:
            d=search.backend.dispatch
            self.assertEqual((d.capacity,d.queue[2],d.trace[2],d.targets[2]),(16384,16384*44,16384*64,16384*32))
            self.assertEqual(d.tables.read(d.targets[1],4096*32,32),self.job.share_bound.to_bytes(32,'little'))
    def test_large_decoder_complete_overflow_duplicates_and_stale(self):
        bound=(1<<256)-1;generation=(1<<63)+3;count=16384
        raw=b''.join(struct.pack('<3I',i,generation&0xffffffff,generation>>32)+bytes(32)for i in range(count))
        result=decode(raw,struct.pack('<2I',count,0),count,bound,count,generation)
        self.assertEqual(len(result.require_complete()),count)
        result=decode(raw[:44],struct.pack('<2I',count,1),count,bound,1,generation);self.assertTrue(result.overflow)
        with self.assertRaises(ValueError):decode(raw[:44]*2,struct.pack('<2I',2,0),count,bound,2,generation)
        with self.assertRaises(ValueError):decode(raw[:44],struct.pack('<2I',1,0),count,bound,1,generation+1)
        for value in (0,16385,True):
            with self.assertRaises(ValueError):validate(value,bound,0,generation)

if __name__=='__main__':unittest.main()
