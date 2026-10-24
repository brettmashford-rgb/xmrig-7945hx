"""Range coverage, bounded batching, overflow and generation/cursor tests. ISC."""
import random
import unittest
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain,RangePlan,RangeCursor,run_range
from tools.check_tile_scan_gpu import ScanResult


class TileRangeTests(unittest.TestCase):
    def test_random_access_matches_brute_force_offsets_and_large_period(self):
        rng=random.Random(506015)
        patterns=[PeriodicPattern(bytes(6)),PeriodicPattern.from_list([0,1,8,9,16,17,24,25,32,33]),
                  PeriodicPattern.from_list([0,1,8,9,32,33,40,41,64,65,72,73,96,97,104,105]),
                  PeriodicPattern(bytes.fromhex('ff01ff010000')),
                  PeriodicPattern(bytes.fromhex('020103010102'))]
        for pattern in patterns:
            for dimension in [1,2,33,128,513,*[rng.randrange(1,1000)for _ in range(12)]]:
                domain=PatternDomain(dimension,pattern)
                expected=[i for i in range(max(0,dimension-pattern.to_list()[-1]))if pattern.offset_is_valid(i)]
                self.assertEqual(domain.count,len(expected))
                self.assertEqual([domain.offset(i)for i in range(domain.count)],expected)
        # This domain has a huge gap-residue count; construction must not build a list.
        domain=PatternDomain(0xffffffff,PeriodicPattern(bytes.fromhex('ff01ff010000')))
        self.assertTrue(domain.pattern.offset_is_valid(domain.offset(domain.count-1)))
        self.assertLess(domain.indices(domain.count-1)[-1],domain.dimension)

    def test_production_domain_and_every_small_batch_map(self):
        a=PeriodicPattern.from_list([0,1,8,9,16,17,24,25,32,33])
        b=PeriodicPattern.from_list([0,1,8,9,32,33,40,41,64,65,72,73,96,97,104,105])
        plan=RangePlan(PatternDomain(5121,a),PatternDomain(262144,b))
        self.assertEqual((plan.a.count,plan.b.count,plan.count),(512,16384,8388608))
        for start in (0,plan.count//2,plan.count-7):
            end=min(plan.count,start+7);seen=[]
            for batch in plan.batches(start,end):
                self.assertLessEqual(len(batch.rows),32);self.assertLessEqual(len(batch.cols),32)
                for i,(ra,cb)in enumerate(batch.maps):
                    tile=batch.start+i;seen.append(tile)
                    self.assertEqual((tuple(batch.rows[j]for j in ra),tuple(batch.cols[j]for j in cb)),plan.indices(tile))
            self.assertEqual(seen,list(range(start,end)))
        with self.assertRaises(ValueError):list(plan.batches(0,plan.count+1))

    def test_overflow_retry_cancel_resume_and_failed_delivery_cursor(self):
        single=PeriodicPattern(bytes(6));plan=RangePlan(PatternDomain(3,single),PatternDomain(5,single),batch_queries=4)
        cursor=RangeCursor(7,0,plan.count);generation=[7];delivered=[];calls=[]
        def backend(batch,capacity,tag):
            calls.append((batch.start,capacity,tag));n=len(batch.maps)
            return ScanResult(n,n>capacity,{i:bytes([i])*32 for i in range(min(n,capacity))})
        def deliver(records):
            delivered.extend(records)
            if len(delivered)==4:generation[0]=8
        run_range(plan,cursor,backend,lambda:generation[0],deliver)
        self.assertEqual((cursor.status,cursor.next_tile,cursor.retries),('cancelled',4,1))
        generation[0]=7;run_range(plan,cursor,backend,lambda:generation[0],delivered.extend)
        self.assertEqual(cursor.status,'complete');self.assertEqual(cursor.next_tile,15)
        self.assertEqual([i for i,_,_ in delivered],list(range(15)))
        self.assertEqual(cursor.retries,4)
        # Cancellation after a launch discards that batch, including its partial queue.
        cursor=RangeCursor(7,0,2)
        def cancelled_backend(batch,capacity,tag):
            generation[0]=8;return backend(batch,capacity,tag)
        run_range(plan,cursor,cancelled_backend,lambda:generation[0],lambda r:self.fail('stale delivery'))
        self.assertEqual((cursor.status,cursor.next_tile),('cancelled',0))
        cursor=RangeCursor(7,0,2);generation[0]=7
        def failed(records):raise RuntimeError('delivery failed')
        with self.assertRaises(RuntimeError):run_range(plan,cursor,backend,lambda:7,failed)
        self.assertEqual(cursor.next_tile,0)
        with self.assertRaises(ValueError):run_range(plan,cursor,backend,lambda:True,delivered.extend)

    def test_constant_profile_tail_and_memory_bounds(self):
        from tools.check_range_scan_gpu import ConstantProfile
        single=PeriodicPattern(bytes(6));plan=RangePlan(PatternDomain(3,single),PatternDomain(5,single))
        tail=bytes([192,64]*8)
        profile=ConstantProfile(3,5,1056,32,64,tail,bytes(32),bytes(32))
        batch=next(plan.batches(0,15));case=profile.case(batch)
        self.assertEqual(case.signal_a[-16:],[-64,64]*8)
        self.assertEqual(case.signal_a[:-16],[64]*(3*1056-16))
        self.assertEqual(case.signal_b,[64]*(5*1056))
        with self.assertRaises(ValueError):ConstantProfile(3,5,1056,32,64,bytes([65]*16),bytes(32),bytes(32))
        with self.assertRaises(ValueError):ConstantProfile(3,262145,32768,128,64,tail,bytes(32),bytes(32))


if __name__=='__main__':unittest.main()
