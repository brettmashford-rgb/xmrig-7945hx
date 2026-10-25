"""Persistent nonce-cache ownership, exact cursors and cancellation. ISC."""
from types import SimpleNamespace
import unittest

from pool.search import NonceSearch, StaleWork
from pool.session import MiningProfile, PoolSession
from reference.patterns import PeriodicPattern
from tools.check_tile_scan_gpu import ScanResult


class PersistentSearchTests(unittest.TestCase):
    def setUp(self):
        pattern = PeriodicPattern.from_list([0, 1, 8, 9, 64, 65, 72, 73])
        self.session = PoolSession(MiningProfile(256, 256, 4096, 128, pattern, pattern), cert_version=3)
        self.message = {'id': -1, 'status': 1, 'result': ['notify', bytes(200).hex(),
                        (1 << 200).to_bytes(32, 'little').hex(), bytes(8).hex(), '3']}
        self.session.consume({'id': 0, 'status': 1, 'result': True})
        self.session.consume({'id': -1, 'status': 1, 'result': ['extranonce', bytes(8).hex()]})
        self.job = self.session.consume(self.message)
        self.context = SimpleNamespace(job=self.job, profile=object())
        self.created = []; self.calls = []
        owner = self
        class Backend:
            def __init__(backend, profile, device, *, bound):
                owner.assertIs(profile, owner.context.profile)
                owner.assertEqual(bound, owner.job.share_bound)
                backend.closed = 0; owner.created.append(backend)
            def __call__(backend, batch, capacity, generation):
                owner.assertEqual(generation, owner.job.generation)
                owner.calls.append((batch.start, batch.stop, capacity))
                return ScanResult(0, False, {})
            def close(backend): backend.closed += 1
        self.Backend = Backend

    def create(self, **kwargs):
        return NonceSearch(self.context, None, self.session.is_current,
                           backend_factory=kwargs.pop('backend_factory', self.Backend), **kwargs)

    def test_two_windows_reuse_one_cache_and_exact_global_cursor(self):
        with self.create() as search:
            self.assertGreater(search.plan.count, 140)
            hit, cursor = search.advance(70)
            self.assertIsNone(hit); self.assertEqual(cursor.next_tile, 70)
            self.assertEqual(self.created[0].closed, 0)
            hit, cursor = search.advance(70)
            self.assertEqual(cursor.next_tile, 140); self.assertEqual(cursor.batches_done, 4)
            self.assertEqual(self.calls, [(0,64,1), (64,70,1), (70,134,1), (134,140,1)])
            self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0].closed, 1)
        search.close(); self.assertEqual(self.created[0].closed, 1)

    def test_overflow_retry_does_not_recreate_cache_or_duplicate_hit(self):
        parent = self.Backend
        owner = self
        class Overflow(parent):
            def __call__(backend, batch, capacity, generation):
                owner.calls.append((batch.start,batch.stop,capacity))
                return ScanResult(2, capacity < 2, {1:bytes(32),3:bytes(32)} if capacity>=2 else {1:bytes(32)})
        with self.create(start=10, backend_factory=Overflow) as search:
            hit, cursor = search.advance(8)
            self.assertEqual((hit.tile, cursor.next_tile, cursor.retries), (11,18,1))
            self.assertEqual(self.calls, [(10,18,1), (10,18,8)])
            self.assertEqual(len(self.created), 1)
            with self.assertRaises(ValueError): search.advance(8)
            self.assertEqual(len(self.calls), 2)

    def test_replacement_between_windows_closes_without_dispatch(self):
        search = self.create(); search.advance(2)
        self.session.consume(self.message)
        with self.assertRaises(StaleWork): search.advance(2)
        self.assertEqual(self.calls, [(0,2,1)]); self.assertEqual(search.cursor.next_tile, 2)
        self.assertTrue(search.closed); self.assertEqual(self.created[0].closed, 1)
        with self.assertRaises(ValueError): search.advance(2)

    def test_dispatch_failure_keeps_last_committed_cursor_and_closes(self):
        parent = self.Backend
        class Failing(parent):
            def __call__(backend, batch, capacity, generation):
                if batch.start == 64: raise RuntimeError('controlled dispatch failure')
                return super().__call__(batch,capacity,generation)
        search = self.create(backend_factory=Failing)
        with self.assertRaises(RuntimeError): search.advance(70)
        self.assertEqual(search.cursor.next_tile, 64)
        self.assertTrue(search.closed); self.assertEqual(self.created[0].closed, 1)

    def test_replacement_during_cache_setup_closes_owned_cache(self):
        parent = self.Backend
        owner = self
        class Replacing(parent):
            def __init__(backend, *args, **kwargs):
                super().__init__(*args, **kwargs); owner.session.reset()
        with self.assertRaises(StaleWork): self.create(backend_factory=Replacing)
        self.assertEqual(self.created[0].closed, 1); self.assertEqual(self.calls, [])

    def test_domain_end_clamps_and_empty_window_has_no_dispatch(self):
        with self.create() as search:
            for size in (-1, True, 1.5):
                with self.assertRaises(ValueError): search.advance(size)
            search.advance(0); self.assertEqual(self.calls, [])
            _, cursor = search.advance(search.plan.count+100)
            self.assertEqual(cursor.next_tile, search.plan.count)
            self.assertEqual(cursor.status, 'complete')
            launches = len(self.calls); search.advance(1)
            self.assertEqual(len(self.calls), launches)
            self.assertEqual(len(self.created), 1)


if __name__ == '__main__': unittest.main()
