"""Explicit profile limits, target bounds and stale pool-job state. ISC."""
import itertools
import unittest

from pool.job import _HEADER_MASK, _SCRAMBLE_KEY
from pool.session import MAX_U256, MiningProfile, PoolSession
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern


def profile():
    pattern = PeriodicPattern.from_list([0, 1, 8, 9, 64, 65, 72, 73])
    return MiningProfile(128, 128, 4096, 128, pattern, pattern)


def notify(header=bytes(76), *, target=1 << 200, tail=bytes(124), token=bytes(8), marker='3'):
    payload = bytes(value ^ _HEADER_MASK[i] ^ _SCRAMBLE_KEY[i % 32]
                    for i, value in enumerate(header)) + tail
    return {'id': -1, 'status': 1, 'result': ['notify', payload.hex(),
            target.to_bytes(32, 'little').hex(), token.hex(), marker]}


LOGIN = {'id': 0, 'status': 1, 'result': True}
EXTRA = {'id': -1, 'status': 1, 'result': ['extranonce', bytes(range(8)).hex()]}


class PoolSessionTests(unittest.TestCase):
    def test_all_handshake_orderings_require_all_inputs(self):
        for messages in itertools.permutations((LOGIN, EXTRA, notify())):
            session = PoolSession(profile(), cert_version=3)
            session.consume(messages[0]); self.assertIsNone(session.snapshot())
            session.consume(messages[1]); self.assertIsNone(session.snapshot())
            job = session.consume(messages[2])
            self.assertTrue(session.is_current(job))
            self.assertEqual(job.assigned_extranonce, bytes(range(8)))
            self.assertEqual(job.header, bytes(76))
            self.assertEqual(job.job_key, small_hash(bytes(76)+profile().config))
            self.assertEqual(job.share_bound, (1 << 200)*8*8*4096)
            self.assertIs(session.consume(LOGIN), job)

    def test_each_job_update_invalidates_snapshots(self):
        session = PoolSession(profile(), cert_version=3)
        session.consume(LOGIN); session.consume(EXTRA)
        first = session.consume(notify())
        second = session.consume(notify(tail=bytes([17])*124, token=bytes([2])*8))
        self.assertFalse(session.is_current(first))
        self.assertTrue(session.is_current(second))
        self.assertGreater(second.generation, first.generation)
        self.assertEqual(second.job_key, first.job_key)
        self.assertNotEqual(second.opaque_metadata, first.opaque_metadata)
        third = session.consume(notify(header=bytes([1])+bytes(75)))
        self.assertNotEqual(third.job_key, second.job_key)
        self.assertFalse(session.is_current(second))
        fourth = session.consume(notify(header=third.header, target=1 << 199))
        self.assertEqual(fourth.job_key, third.job_key)
        self.assertEqual(fourth.share_bound*2, third.share_bound)
        self.assertFalse(session.is_current(third))
        fifth = session.consume({'id': -1, 'status': 1, 'result': ['extranonce', (bytes([3])*8).hex()]})
        self.assertTrue(session.is_current(fifth))
        self.assertFalse(session.is_current(fourth))

    def test_bad_notify_rejects_and_clears_old_work(self):
        for bad in (notify(target=0), notify(target=MAX_U256), notify(marker='2'),
                    {'id': -1, 'status': 1, 'result': ['unknown-job-schema']},
                    {'id': -1, 'status': 1, 'result': ['extranonce', 'bad']},
                    {'id': -1, 'status': 1, 'result': ['notify', 'bad', 'bad', 'bad', '3']}):
            session = PoolSession(profile(), cert_version=3)
            session.consume(LOGIN); session.consume(EXTRA)
            job = session.consume(notify())
            with self.assertRaises(ValueError):
                session.consume(bad)
            self.assertIsNone(session.snapshot())
            self.assertFalse(session.is_current(job))

    def test_reset_close_and_login_rejection(self):
        session = PoolSession(profile(), cert_version=3)
        session.consume(LOGIN); session.consume(EXTRA); job = session.consume(notify())
        session.reset()
        self.assertFalse(session.is_current(job)); self.assertIsNone(session.snapshot())
        session.consume(notify()); session.consume(EXTRA)
        self.assertIsNone(session.snapshot())
        session.consume(LOGIN); self.assertIsNotNone(session.snapshot())
        session.close(); self.assertIsNone(session.snapshot())
        with self.assertRaises(ValueError): session.consume(notify())
        session.reset()
        with self.assertRaises(ValueError): session.consume({'id': 0, 'status': 1, 'result': False})
        self.assertTrue(session.closed)

    def test_share_target_overflow_boundary_and_profile_limits(self):
        p = profile(); factor = 8*8*4096
        limit = MAX_U256//factor
        self.assertEqual(p.share_bound(limit.to_bytes(32, 'little')), limit*factor)
        for value in (0, limit+1):
            with self.assertRaises(ValueError): p.share_bound(value.to_bytes(32, 'little'))
        for m, n, k, rank in ((True, 128, 4096, 128), (128, 128, 1024, 128),
                              (128, 128, 4096, 64), (128, 128, 4097, 128),
                              (1 << 25, 128, 4096, 128), (128, 128, 65536, 256)):
            with self.assertRaises(ValueError): MiningProfile(m, n, k, rank, p.rows, p.cols)
        with self.assertRaises(ValueError): PoolSession(p, cert_version=2)


if __name__ == '__main__':
    unittest.main()
