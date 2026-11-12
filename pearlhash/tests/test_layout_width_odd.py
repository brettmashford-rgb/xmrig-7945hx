"""Real odd-column dispatch bindings, partial queues, canonical hits and retained ownership. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import patch
from tools.check_layout_width import odd_column_session
from tools.layout_width_scan import new_search,canonical
from tools.job_geometry import JobGeometry
from tools.job_b_tables import JobBTables
from test_job_b_tables import Device
from test_prepared_dispatch import profile
class Odd(unittest.TestCase):
    def test_second_column_only_last_unpaired_column_and_boundary_retries(self):
        for mode in ('pair-direct','layout-col4','layout-col8'):
            session,job=odd_column_session(bytes(32));device=Device()
            p=replace(profile(),m=160,n=234);context=SimpleNamespace(job=job,profile=p)
            b=JobBTables(device,context,session.is_current);g=JobGeometry(device,job,session.is_current,maps=True)
            try:
                self.assertEqual((len(g.plan.rows),len(g.plan.cols)),(16,9))
                for first,count in ((31,2),(32,1),(64,16),(143,1),(71,7)):
                    with new_search(context,device,session.is_current,b,g,start=first,mode=mode)as search:
                        d=search.backend.dispatch
                        self.assertGreaterEqual(d.grid(count,first),1)
                        def emit():
                            cap=d.queue_capacity.value
                            device.write_bytes(d.status[1].value,struct.pack('<2I',count,int(cap<count)))
                            device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,job.generation,0)+bytes(32)for i in range(min(count,cap))))
                        device.after_launch=emit
                        with patch('tools.layout_width_scan.global_reference',return_value=[(bytes(64),bytes(32))]):
                            hit,cursor=search.advance(count)
                        self.assertEqual(hit.tile,canonical(search.plan,mode,first))
                        self.assertEqual(cursor.next_tile,first+count);self.assertEqual(cursor.retries,int(count>1))
                        device.after_launch=None
                    self.assertFalse(g.leased);self.assertFalse(b.leased)
            finally:g.close();b.close();session.close()
            self.assertFalse(device.allocations)
if __name__=='__main__':unittest.main()
