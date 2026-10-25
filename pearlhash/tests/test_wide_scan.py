"""Large descriptor/queue bounds and generation-gated wide plans. ISC."""
import struct
from types import SimpleNamespace
import unittest

from pool.search import NonceSearch
from pool.session import MiningProfile, PoolSession
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import MAX_BOUND, ScanResult, TileQuery
from tools.global_range import GlobalRangePlan
from tools.virtual_scan import pack_global_queries
from tools.wide_scan import (WideBatch, WideRangePlan, WideCandidateBackend,
                             decode_wide, pack_wide, validate_wide, wide_plan_for)


class WideScanTests(unittest.TestCase):
    def profile(self):
        return ConstantProfile(3,7,1024,32,64,bytes(16),bytes(32),bytes([1])*32)

    def test_max_descriptor_payload_preserves_existing_layout(self):
        profile=self.profile();q=TileQuery((0,2),(1,6));queries=(q,)*4096
        packed=pack_wide(profile,queries)
        self.assertEqual(len(packed),4096*66*4)
        self.assertEqual(packed,pack_global_queries(profile,(q,))*4096)
        with self.assertRaises(ValueError):pack_wide(profile,queries+(q,))
        with self.assertRaises(ValueError):pack_wide(profile,(TileQuery((3,),(0,)),))

    def test_full_queue_accepts_high_slots_and_unordered_records(self):
        generation=(1<<63)+5
        raw=b''.join(struct.pack('<IQ',i,generation)+i.to_bytes(32,'little') for i in reversed(range(4096)))
        result=decode_wide(raw,struct.pack('<2I',4096,0),[MAX_BOUND]*4096,4096,generation)
        self.assertEqual(len(result.records),4096)
        self.assertEqual(result.records[4095],(4095).to_bytes(32,'little'))
        for status in (struct.pack('<2I',4097,1),struct.pack('<2I',4096,1)):
            with self.assertRaises(ValueError):decode_wide(raw,status,[MAX_BOUND]*4096,4096,generation)
        for changed in (raw[:44]+raw[:44]+raw[88:],struct.pack('<IQ',4096,generation)+raw[12:],
                        struct.pack('<IQ',4095,generation+1)+raw[12:]):
            with self.assertRaises(ValueError):decode_wide(changed,struct.pack('<2I',4096,0),[MAX_BOUND]*4096,4096,generation)
        with self.assertRaises(ValueError):decode_wide(raw,struct.pack('<2I',4096,0),[0]*4096,4096,generation)
        partial=decode_wide(b'',struct.pack('<2I',4096,1),[MAX_BOUND]*4096,0,generation)
        self.assertEqual(partial.records,{})
        with self.assertRaises(RuntimeError):partial.require_complete()

    def test_limits_and_no_cpu_fallback(self):
        for bounds,capacity,gen in (([],0,0),([0]*4097,0,0),([0],True,0),([0],4097,0),
                                    ([-1],0,0),([1<<256],0,0),([0],0,1<<64)):
            with self.assertRaises(ValueError):validate_wide(bounds,capacity,gen)
        with self.assertRaises(ValueError):WideCandidateBackend(self.profile(),None)

    def test_wide_global_plan_preserves_production_row_boundary(self):
        rows=PeriodicPattern(bytes.fromhex('000103040000'))
        cols=PeriodicPattern(bytes.fromhex('000103010103'))
        a=PatternDomain(5121,rows);b=PatternDomain(262144,cols)
        plan=WideRangePlan(a,b);old=GlobalRangePlan(a,b)
        self.assertEqual(plan.count,8388608)
        first=b.count-1;batch=next(plan.batches(first,first+4096))
        self.assertIsInstance(batch,WideBatch);self.assertEqual(len(batch.maps),4096)
        for offset in (0,1,63,64,4095):self.assertEqual(batch.maps[offset],old.indices(first+offset))
        with self.assertRaises(ValueError):WideRangePlan(a,b,batch_queries=4097)

    def test_wide_nonce_engine_retries_without_truncating_global_ids(self):
        pattern=PeriodicPattern.from_list([0,1,8,9,64,65,72,73])
        session=PoolSession(MiningProfile(256,256,4096,128,pattern,pattern),cert_version=3)
        session.consume({'id':0,'status':1,'result':True})
        session.consume({'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]})
        job=session.consume({'id':-1,'status':1,'result':['notify',bytes(200).hex(),(1<<200).to_bytes(32,'little').hex(),bytes(8).hex(),'3']})
        calls=[];closed=[]
        class Backend:
            def __init__(self,*a,**k):pass
            def __call__(self,batch,capacity,generation):
                calls.append((batch,capacity))
                return ScanResult(2,capacity<2,{64:bytes(32),129:bytes(32)} if capacity>=2 else {64:bytes(32)})
            def close(self):closed.append(True)
        with NonceSearch(SimpleNamespace(job=job,profile=object()),None,session.is_current,
                         backend_factory=Backend,plan_factory=wide_plan_for) as search:
            self.assertGreater(search.plan.count,129);self.assertLessEqual(search.plan.count,4096)
            hit,cursor=search.advance(search.plan.count)
            self.assertEqual(hit.tile,64);self.assertEqual(cursor.retries,1)
            self.assertEqual(cursor.next_tile,search.plan.count)
        self.assertEqual([cap for _,cap in calls],[1,search.plan.count])
        self.assertEqual(closed,[True])


if __name__=='__main__':unittest.main()
