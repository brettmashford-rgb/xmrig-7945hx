"""Global-index planning and cursor failure gates. ISC."""
import unittest

from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain, RangeBatch, RangeCursor, RangePlan, run_range
from tools.check_tile_scan_gpu import ScanResult
from tools.global_range import GlobalBatch, GlobalRangePlan, GlobalRangeBackend


class GlobalRangeTests(unittest.TestCase):
    def plan(self, m=3, n=70, cap=64):
        single = PeriodicPattern(bytes(6))
        return GlobalRangePlan(PatternDomain(m, single), PatternDomain(n, single), batch_queries=cap)

    def test_global_order_and_batch_limits(self):
        plan = self.plan()
        batches = list(plan.batches(60, 190))
        self.assertEqual([len(b.maps) for b in batches], [64, 64, 2])
        for batch in batches:
            self.assertEqual(list(batch.maps), [plan.indices(i) for i in range(batch.start, batch.stop)])
        self.assertGreater(len({col for _, cols in batches[0].maps for col in cols}), 32)
        self.assertEqual(list(plan.batches(210, 210)), [])
        for cap in (1, 7, 64):
            p = self.plan(cap=cap)
            self.assertEqual(sum(len(b.maps) for b in p.batches(0, p.count)), p.count)

    def test_production_boundary_and_legacy_indices(self):
        rows = PeriodicPattern.from_list([0, 1, 8, 9, 16, 17, 24, 25, 32, 33])
        cols = PeriodicPattern.from_list([0, 1, 8, 9, 32, 33, 40, 41, 64, 65, 72, 73, 96, 97, 104, 105])
        a, b = PatternDomain(5121, rows), PatternDomain(262144, cols)
        plan, old = GlobalRangePlan(a, b), RangePlan(a, b)
        self.assertEqual(plan.count, 8388608)
        for start in (0, b.count - 2, plan.count // 2, plan.count - 64):
            batch = next(plan.batches(start, start + 64))
            self.assertEqual(len(batch.maps), 64)
            self.assertEqual(batch.maps, tuple(old.indices(i) for i in range(start, start + 64)))

    def test_invalid_batches(self):
        for args in ((0, 0, ()), (0, 65, (((0,), (0,)),) * 65),
                     (True, 2, (((0,), (0,)),)), (0, 1, (((False,), (0,)),)),
                     (0, 1, (((0,), (1 << 32,)),)), (0, 1, (((), (0,)),))):
            with self.assertRaises(ValueError):
                GlobalBatch(*args)
        for start, stop in ((-1, 2), (0, 211), (True, 2), (3, 2)):
            with self.assertRaises(ValueError):
                list(self.plan().batches(start, stop))

    def test_overflow_and_failed_delivery_do_not_commit(self):
        plan = self.plan()
        cursor = RangeCursor(18, 0, 65)
        calls = []
        def backend(batch, capacity, generation):
            calls.append(capacity)
            records = {i: i.to_bytes(32, 'little') for i in range(min(len(batch.maps), capacity))}
            return ScanResult(len(batch.maps), len(batch.maps) > capacity, records)
        def fail(records):
            raise RuntimeError('delivery failed')
        with self.assertRaises(RuntimeError):
            run_range(plan, cursor, backend, lambda: 18, fail)
        self.assertEqual(cursor.next_tile, 0)
        self.assertEqual(calls, [1, 64])
        seen = []
        run_range(plan, cursor, backend, lambda: 18, seen.extend)
        self.assertEqual([r[0] for r in seen], list(range(65)))
        self.assertEqual(cursor.status, 'complete')

    def test_global_backend_rejects_local_pool_batch(self):
        # No CUDA context or hash operation is needed to reject the wrong ABI.
        backend = object.__new__(GlobalRangeBackend)
        backend.closed = False
        with self.assertRaises(ValueError):
            backend(RangeBatch(0, 1, (0,), (0,), (((0,), (0,)),)), 1, 18)


if __name__ == '__main__':
    unittest.main()
