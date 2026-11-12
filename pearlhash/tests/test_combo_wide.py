"""A real 16384-record host queue, independent CPU verification and retry crediting. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import patch
from pool.session import MiningProfile
from tools.check_prepared_job import synthetic_session
from tools.combo_scan import new_search,MODES
from tools.job_geometry import JobGeometry
from tools.job_b_tables import JobBTables
from test_prepared_dispatch import profile
from test_job_b_tables import Device

class Wide(unittest.TestCase):
    def test_complete_16384_retry_and_full_extent_guards(self):
        for mode in MODES:
            with self.subTest(mode=mode):self.exercise(mode)
    def exercise(self,mode):
        with patch('tools.check_prepared_job.MiningProfile',side_effect=lambda m,n,k,r,rows,cols:MiningProfile(160,16384,k,r,rows,cols)):
            session,job,_=synthetic_session(bytes(32))
        device=Device();p=replace(profile(),m=160,n=16384);context=SimpleNamespace(job=job,profile=p)
        b=JobBTables(device,context,session.is_current);g=JobGeometry(device,job,session.is_current,maps=True)
        try:
            with new_search(context,device,session.is_current,b,g,mode=mode)as search:
                d=search.backend.dispatch;caps=[]
                def emit():
                    cap=d.queue_capacity.value;caps.append(cap)
                    device.write_bytes(d.status[1].value,struct.pack('<2I',16384,int(cap<16384)))
                    device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,job.generation,0)+bytes(32)for i in range(min(cap,16384))))
                device.after_launch=emit
                with patch('tools.combo_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
                    hit,cursor=search.advance(16384)
                    self.assertEqual((cursor.next_tile,cursor.retries,hit.tile),(16384,1,0));self.assertEqual(caps,[1,16384])
                    self.assertEqual(reference.call_count,16384);self.assertEqual(device.verified_tiles,16384)
                device.after_launch=None
        finally:g.close();b.close();session.close()
        self.assertFalse(device.allocations)

if __name__=='__main__':unittest.main()
