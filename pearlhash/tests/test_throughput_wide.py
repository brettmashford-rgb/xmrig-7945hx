"""A real limit-record host queue, independent CPU verification and retry crediting. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import patch
from pool.session import MiningProfile
from tools.check_prepared_job import synthetic_session
from tools.throughput_scan import new_search,MODES,LIMITS
from tools.job_geometry import JobGeometry
from tools.job_b_tables import JobBTables
from test_prepared_dispatch import profile
from test_job_b_tables import Device

class Wide(unittest.TestCase):
    def test_complete_full_limit_retry_and_full_extent_guards(self):
        for mode in MODES:
            with self.subTest(mode=mode):self.exercise(mode)
    def exercise(self,mode):
        with patch('tools.check_prepared_job.MiningProfile',side_effect=lambda m,n,k,r,rows,cols:MiningProfile(640,16384,k,r,rows,cols)):
            session,job,_=synthetic_session(bytes(32))
        device=Device();p=replace(profile(),m=640,n=16384);context=SimpleNamespace(job=job,profile=p)
        b=JobBTables(device,context,session.is_current);g=JobGeometry(device,job,session.is_current,maps=True)
        try:
            with new_search(context,device,session.is_current,b,g,mode=mode)as search:
                d=search.backend.dispatch;caps=[];limit=LIMITS[mode]
                self.assertEqual(d.capacity,limit)
                self.assertEqual([d.desc[2],d.targets[2],d.queue[2],d.trace[2]],[limit*x for x in (264,32,44,64)])
                from tools.throughput_scan import Batch
                with self.assertRaises(ValueError):d.prepare_window(Batch(search.plan,0,limit+1))
                one=Batch(search.plan,0,1)
                with self.assertRaises(ValueError):d.scan_window(one,d.prepare_window(one),job.generation,capacity=limit+1)
                def emit():
                    cap=d.queue_capacity.value;caps.append(cap)
                    device.write_bytes(d.status[1].value,struct.pack('<2I',limit,int(cap<limit)))
                    device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,job.generation,0)+bytes(32)for i in range(min(cap,limit))))
                device.after_launch=emit
                with patch('tools.throughput_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
                    hit,cursor=search.advance(limit)
                    self.assertEqual((cursor.next_tile,cursor.retries,hit.tile),(limit,1,0));self.assertEqual(caps,[1,limit])
                    self.assertEqual(reference.call_count,limit);self.assertEqual(device.verified_tiles,limit)
                device.after_launch=None
        finally:g.close();b.close();session.close()
        self.assertFalse(device.allocations)

if __name__=='__main__':unittest.main()
