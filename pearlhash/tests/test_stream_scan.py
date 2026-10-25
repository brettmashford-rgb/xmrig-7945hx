"""Split-phase stream ordering, isolation and failure ownership. ISC."""
import ctypes as C
import unittest
from tools.stream_scan import StreamDispatch,execute_pair
from tools.prepared_dispatch import KERNELS
from tools.check_tile_scan_gpu import TileQuery
from test_prepared_dispatch import FakeDevice,FakeTables


class Device(FakeDevice):
    def __init__(self):super().__init__();self.handles=100;self.events=[]
    def api(self,name,types,*args):
        if name=='cuStreamCreate':
            self.handles+=1;C.cast(args[0],C.POINTER(C.c_void_p))[0]=self.handles
            self.assert_flags=args[1]
        if name=='cuLaunchKernel':self.events.append(('launch',args[8].value))
        elif name=='cuStreamSynchronize':self.events.append(('wait',args[0].value))
        elif name=='cuMemcpyHtoD_v2':self.events.append(('upload',args[0].value))
        elif name=='cuStreamDestroy_v2':self.events.append(('destroy',args[0].value))
        super().api(name,types,*args)


class Streams(unittest.TestCase):
    def setUp(self):
        self.device=Device();self.tables=FakeTables(self.device)
        self.lanes=[StreamDispatch(self.device,self.tables,KERNELS[0],capacity=0)for _ in range(2)]
        query=TileQuery(tuple(range(10)),tuple(range(16)))
        self.batches=[lane.prepare([query]*9,[0]*9)for lane in self.lanes]
    def tearDown(self):
        for lane in self.lanes:lane.close()
    def test_both_launches_precede_wait_or_readback(self):
        self.device.events.clear()
        results=execute_pair(self.lanes,self.batches,1<<63,True)
        events=[x[0]for x in self.device.events]
        self.assertEqual(events[:6],['upload']*6)
        self.assertEqual(events[6:],['launch','launch','wait','wait'])
        self.assertTrue(all(result.total==0 for result,_ in results))
        self.assertNotEqual(self.lanes[0].stream.value,self.lanes[1].stream.value)
        self.assertEqual(self.device.assert_flags,1)
        self.assertTrue(set(x.value for x in self.lanes[0].owned).isdisjoint(x.value for x in self.lanes[1].owned))
    def test_serial_control_waits_between_launches(self):
        self.device.events.clear();execute_pair(self.lanes,self.batches,1,False)
        self.assertEqual([x[0]for x in self.device.events if x[0]!='upload'],['launch','wait','launch','wait'])
    def test_pending_batch_cannot_be_overwritten_or_relaunched(self):
        lane=self.lanes[0];batch=self.batches[0]
        lane.stage(batch,1);lane.enqueue()
        with self.assertRaises(ValueError):lane.stage(batch,2)
        with self.assertRaises(ValueError):lane.enqueue()
        lane.wait()
        with self.assertRaises(ValueError):lane.enqueue()
        lane.finish()
        with self.assertRaises(ValueError):lane.finish()
    def test_foreign_and_closed_batches_rejected(self):
        with self.assertRaisesRegex(ValueError,'foreign'):self.lanes[1].stage(self.batches[0],1)
        self.lanes[0].close()
        with self.assertRaises(ValueError):self.lanes[0].stage(self.batches[0],1)
    def test_cleanup_drains_before_destroy_and_frees_only_own_buffers(self):
        lane=self.lanes[0];other=list(self.lanes[1].owned)
        lane.stage(self.batches[0],1);lane.enqueue();self.device.events.clear();lane.close();lane.close()
        self.assertEqual([x[0]for x in self.device.events],['wait','destroy'])
        self.assertEqual(self.device.allocations,other);self.assertFalse(self.tables.closed)
    def test_launch_error_retains_pending_for_cleanup(self):
        lane=self.lanes[0];lane.stage(self.batches[0],1)
        self.device.after_launch=lambda:(_ for _ in ()).throw(RuntimeError('launch failure'))
        with self.assertRaises(RuntimeError):lane.enqueue()
        self.assertTrue(lane.pending);self.device.after_launch=None
        lane.close();self.assertFalse(lane.pending)
    def test_guard_corruption_is_detected_after_stream_wait(self):
        lane=self.lanes[0];lane.stage(self.batches[0],1);lane.enqueue()
        self.device.memory[lane.desc[0].value][-1]=0
        with self.assertRaisesRegex(RuntimeError,'guard'):lane.finish()


if __name__=='__main__':unittest.main()
