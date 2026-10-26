"""Uniform decoder equivalence, stream ordering, all guards and stale ownership. ISC."""
import ctypes as C
from dataclasses import FrozenInstanceError,replace
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.lean_scan import (LeanBackend,StreamResetBackend,UniformPrepared,decode_uniform,
    uniform_count,validate_uniform,new_lean_search)
from tools.wide_scan import decode_wide
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from test_snapshot_scan import SnapshotDevice,SnapshotTables
from test_prepared_dispatch import profile


class ResetDevice(SnapshotDevice):
    def __init__(self):super().__init__();self.after_reset=None;self.reset_stream=None
    def api(self,name,types,*args):
        if name=='cuStreamCreate':
            self.calls.append(name);C.cast(args[0],C.POINTER(C.c_void_p))[0]=0x1000;return
        if name=='cuLaunchKernel'and self.reset_stream is not None:
            if args[8].value!=self.reset_stream:raise AssertionError('reset/scanner/collector stream differs')
        if name=='cuMemsetD32Async':
            self.calls.append(name);self.reset_stream=args[3].value
            if not self.reset_stream:raise AssertionError('nonblocking scan stream required')
            if args[1]!=0 or args[2]!=2:raise AssertionError('expected eight-byte status clear')
            self.write_bytes(args[0].value,bytes(8))
            if self.after_reset:self.after_reset()
            return
        super().api(name,types,*args)


class Lean(unittest.TestCase):
    backend_type=LeanBackend
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=ResetDevice();self.gen=[self.job.generation]
        self.create()
    def create(self):
        self.tables=SnapshotTables(self.device,self.p)
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=self.backend_type(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
        self.dispatch=self.backend.dispatch
    def tearDown(self):self.backend.close();self.session.close()
    def window(self):return self.backend(FastBatch(self.plan,0,5),1,self.gen[0])
    def test_reset_is_on_scan_stream_before_kernels_without_upload_or_context_wait(self):
        self.device.write_bytes(self.dispatch.status[1].value,struct.pack('<2I',5,1))
        owned=tuple(p.value for p in self.device.allocations);self.device.calls.clear();self.device.reads.clear()
        self.assertEqual(self.window().total,0)
        self.assertEqual(self.device.calls.count('cuMemsetD32Async'),1)
        self.assertEqual(self.device.calls.count('cuMemcpyHtoD_v2'),0)
        self.assertEqual(self.device.calls.count('cuCtxSynchronize'),0)
        self.assertEqual(self.device.calls.count('cuMemcpyDtoH_v2'),1);self.assertEqual(self.device.reads,[504])
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2)
        self.assertLess(self.device.calls.index('cuMemsetD32Async'),self.device.calls.index('cuLaunchKernel'))
        self.assertEqual(tuple(p.value for p in self.device.allocations),owned)
    def test_every_guard_rejects_before_candidate_credit(self):
        for index in range(28):
            if index:self.backend.close();self.create()
            address=self.dispatch.guard_addresses[index];self.device.write_bytes(address,bytes(1))
            with self.subTest(index=index),self.assertRaisesRegex(RuntimeError,'guard'):self.window()
            self.assertEqual(self.device.verified_tiles,0);self.device.write_bytes(address,b'\xa5')
    def test_stale_after_reset_prevents_scanner_and_drains_before_free(self):
        self.device.calls.clear();self.device.after_reset=lambda:self.gen.__setitem__(0,self.gen[0]+1)
        with self.assertRaisesRegex(RuntimeError,'stale'):self.window()
        self.assertTrue(self.dispatch.pending);self.assertNotIn('cuLaunchKernel',self.device.calls)
        self.backend.close();self.assertFalse(self.dispatch.pending);self.assertEqual(self.device.allocations,[])
        self.assertLess(self.device.calls.index('cuStreamSynchronize'),self.device.calls.index('cuStreamDestroy_v2'))
    def test_stale_snapshot_identity_is_rejected(self):
        self.device.after_snapshot=lambda:self.device.write_bytes(self.dispatch.snapshot[1].value+8,bytes(16))
        with self.assertRaisesRegex(RuntimeError,'identity'):self.window()
    def test_complete_queue_still_cpu_checked_and_partial_queue_not_credited(self):
        def queue(total,overflow):
            self.device.write_bytes(self.dispatch.status[1].value,struct.pack('<2I',total,overflow))
            self.device.write_bytes(self.dispatch.queue[1].value,struct.pack('<3I',0,self.gen[0],0)+bytes(32))
        target='tools.lean_scan.global_reference'if self.backend_type is LeanBackend else'tools.snapshot_scan.global_reference'
        with patch(target,return_value=[(bytes(64),bytes(32))])as reference:
            self.device.after_launch=lambda:queue(5,1)
            self.assertTrue(self.window().overflow);reference.assert_not_called()
            self.device.after_launch=lambda:queue(1,0)
            self.assertFalse(self.window().overflow);reference.assert_called_once()
        self.assertEqual(self.device.verified_tiles,1)
    def test_corrupted_candidate_digest_fails_independent_cpu_check(self):
        def queue():
            self.device.write_bytes(self.dispatch.status[1].value,struct.pack('<2I',1,0))
            self.device.write_bytes(self.dispatch.queue[1].value,struct.pack('<3I',0,self.gen[0],0)+bytes(32))
        self.device.after_launch=queue
        target='tools.lean_scan.global_reference'if self.backend_type is LeanBackend else'tools.snapshot_scan.global_reference'
        with patch(target,return_value=[(bytes(64),b'\x01'+bytes(31))]):
            with self.assertRaisesRegex(ValueError,'CPU math'):self.window()
        self.assertEqual(self.device.verified_tiles,0)
    def test_foreign_owner_and_plan_rejected_before_reset(self):
        batch=FastBatch(self.plan,0,5);prepared=self.dispatch.prepare_window(batch)
        self.device.calls.clear()
        foreign=replace(prepared,owner=object())
        with self.assertRaisesRegex(ValueError,'foreign'):self.dispatch.scan_window(batch,foreign,self.gen[0])
        changed=replace(prepared,bound=1)if type(prepared)is UniformPrepared else replace(prepared,bounds=(1,)*5)
        with self.assertRaisesRegex(ValueError,'target'):self.dispatch.scan_window(batch,changed,self.gen[0])
        other=FastBatch(FastPlan.from_job(self.job),0,5)
        with self.assertRaisesRegex(ValueError,'foreign'):self.dispatch.scan_window(other,prepared,self.gen[0])
        self.assertNotIn('cuMemsetD32Async',self.device.calls)
    def test_stale_after_scanner_closes_search_without_cursor_credit(self):
        self.backend.close();self.tables=SnapshotTables(self.device,self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_lean_search(SimpleNamespace(job=self.job,profile=self.p),self.device,lambda job:current[0],lean=self.backend_type is LeanBackend)
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(5)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed)
            self.assertFalse(search.backend.dispatch.pending);self.assertEqual(self.device.allocations,[])
        finally:search.close()


class StreamReset(Lean):backend_type=StreamResetBackend


class Uniform(unittest.TestCase):
    def test_matches_existing_decoder_for_valid_partial_and_complete_queues(self):
        for count in (1,5,67,4096):
            for total in sorted({0,1,min(5,count),count}):
                for capacity in sorted({0,1,min(5,count),count}):
                    for generation in (0,(1<<63)+55,(1<<64)-1):
                        bound=(1<<255)+7;status=struct.pack('<2I',total,int(total>capacity))
                        raw=b''.join(struct.pack('<3I',i,generation&0xffffffff,generation>>32)+(i+1).to_bytes(32,'little')
                            for i in range(min(total,capacity)))+bytes(max(0,capacity-total)*44)
                        self.assertEqual(decode_uniform(raw,status,count,bound,capacity,generation),
                            decode_wide(raw,status,(bound,)*count,capacity,generation))
    def test_all_candidate_rejection_rules_match_existing_decoder(self):
        generation=(1<<63)+9;count=5;bound=7
        valid=struct.pack('<3I',0,generation&0xffffffff,generation>>32)+(7).to_bytes(32,'little')
        cases=[(valid,struct.pack('<2I',6,1),1),(valid,struct.pack('<2I',1,1),1),
            (valid[:-1],struct.pack('<2I',1,0),1),
            (struct.pack('<3I',5,9,1<<31)+bytes(32),struct.pack('<2I',1,0),1),
            (struct.pack('<3I',0,8,1<<31)+bytes(32),struct.pack('<2I',1,0),1),
            (valid[:12]+(8).to_bytes(32,'little'),struct.pack('<2I',1,0),1),
            (valid*2,struct.pack('<2I',2,0),2)]
        for raw,status,capacity in cases:
            with self.assertRaises(ValueError):decode_uniform(raw,status,count,bound,capacity,generation)
            with self.assertRaises(ValueError):decode_wide(raw,status,(bound,)*count,capacity,generation)
    def test_invalid_scalar_types_and_ranges_are_rejected(self):
        for slot,values in enumerate(((True,0,4097),(True,-1,1<<256),(True,-1,4097),(True,-1,1<<64))):
            for value in values:
                args=[5,7,1,55];args[slot]=value
                with self.assertRaises(ValueError):validate_uniform(*args)
    def test_preparation_has_one_immutable_bound_and_no_4096_element_tuple(self):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        device=ResetDevice();p=replace(profile(),m=160,n=192);tables=SnapshotTables(device,p)
        try:
            with patch('tools.resident_scan.VirtualTables',return_value=tables):backend=LeanBackend(p,device,plan=plan,bound=0)
            try:
                batch=FastBatch(plan,0,5);prepared=backend.dispatch.prepare_window(batch)
                self.assertIs(type(prepared),UniformPrepared);self.assertFalse(hasattr(prepared,'bounds'))
                with self.assertRaises(FrozenInstanceError):prepared.bound=1
                with patch('tools.lean_scan.validate_wide',side_effect=AssertionError('repeated target scan')):
                    self.assertEqual(backend(batch,1,1).total,0)
            finally:backend.close()
        finally:session.close()


if __name__=='__main__':unittest.main()
