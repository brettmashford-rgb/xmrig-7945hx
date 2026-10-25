"""Job-driven search bounds, profile binding and stale stage gates. ISC."""
import unittest
from unittest.mock import patch

from pool.search import Hit, StaleWork, prepare_base, prepare_nonce, search_nonce, build_proof, plan_for
from tools.check_job_search import synthetic_session
from tools.check_tile_scan_gpu import ScanResult


class JobSearchTests(unittest.TestCase):
    def setUp(self):
        self.session, self.job, self.message = synthetic_session(bytes(32))
        self.current = self.session.is_current

    def test_explicit_profile_dimensions_nonce_and_base_binding(self):
        base = prepare_base(self.job, self.current)
        context = prepare_nonce(self.job, base, b'TESTWORK', bytes(8), self.current)
        self.assertEqual((context.profile.m, context.profile.n), (160, 192))
        self.assertEqual(base.opening.total_leaves, 192*4096//1024)
        self.assertNotEqual(context.worker, self.job.assigned_extranonce)
        self.assertGreater(plan_for(self.job).count, 64)
        for worker in (None, b'bad', bytes(9)):
            with self.assertRaises(ValueError):
                prepare_nonce(self.job, base, worker, bytes(8), self.current)
        from dataclasses import replace
        with self.assertRaises(ValueError):
            prepare_nonce(self.job, replace(base, n=128), bytes(8), bytes(8), self.current)

    def test_inflight_native_commitment_cannot_publish_stale_base(self):
        from reference.constant_merkle import constant_opening
        def replacing(*args, **kwargs):
            value = constant_opening(*args, **kwargs)
            self.session.reset()
            return value
        with patch('pool.search.constant_opening', side_effect=replacing):
            with self.assertRaises(StaleWork):
                prepare_base(self.job, self.current)

    def test_bound_window_and_closed_backend_on_job_replacement(self):
        base = prepare_base(self.job, self.current)
        context = prepare_nonce(self.job, base, b'TESTWORK', bytes(8), self.current)
        seen = []
        class Backend:
            def __init__(backend, profile, device, *, bound):
                self.assertEqual(bound, self.job.share_bound)
                backend.closed = False
                seen.append(backend)
            def __call__(backend, batch, capacity, generation):
                self.assertEqual((batch.start, batch.stop), (3, 5))
                self.session.consume(self.message)
                return ScanResult(1, False, {0: bytes(32)})
            def close(backend):
                backend.closed = True
        with self.assertRaises(StaleWork):
            search_nonce(context, None, self.current, start=3, stop=5, backend_factory=Backend)
        self.assertTrue(seen[0].closed)
        with patch('pool.search.constant_opening') as native:
            for action in (lambda: prepare_base(self.job, self.current),
                           lambda: prepare_nonce(self.job, base, b'TESTWORK', bytes(8), self.current),
                           lambda: search_nonce(context, None, self.current),
                           lambda: build_proof(context, Hit(self.job.generation, 0, bytes(32)), self.current)):
                with self.assertRaises(StaleWork):
                    action()
            native.assert_not_called()

    def test_target_replacement_is_not_hardcoded_and_cleans_setup(self):
        self.message['result'][2] = (1 << 220).to_bytes(32, 'little').hex()
        job = self.session.consume(self.message)
        base = prepare_base(job, self.current)
        context = prepare_nonce(job, base, b'TESTWORK', bytes(8), self.current)
        seen = []
        class Backend:
            def __init__(backend, profile, device, *, bound):
                self.assertEqual(bound, (1 << 220)*8*8*4096)
                self.assertNotEqual(bound, 1 << 254)
                seen.append(backend)
                backend.closed = False
                self.session.close()
            def __call__(backend, *args):
                self.fail('stale cache setup launched search')
            def close(backend):
                backend.closed = True
        with self.assertRaises(StaleWork):
            search_nonce(context, None, self.current, backend_factory=Backend)
        self.assertTrue(seen[0].closed)


if __name__ == '__main__':
    unittest.main()
