"""Deterministic receiver/worker races and resource lifecycle; no GPU/network. ISC."""
import threading
import unittest

from pool.receiver import PoolReceiver
from pool.search import StaleWork
from pool.worker import LatestJobWorker
from pool.session import MiningProfile, PoolSession
from reference.patterns import PeriodicPattern
from tools.pool_probe import encode


class LiveWorkerTests(unittest.TestCase):
    def setUp(self):
        pattern = PeriodicPattern.from_list([0, 1, 8, 9, 64, 65, 72, 73])
        self.session = PoolSession(MiningProfile(160, 192, 4096, 128, pattern, pattern), cert_version=3)
        self.message = {'id': -1, 'status': 1, 'result': ['notify', bytes(200).hex(),
                        (1 << 236).to_bytes(32, 'little').hex(), bytes(8).hex(), '3']}
        self.session.consume({'id': 0, 'status': 1, 'result': True})
        self.session.consume({'id': -1, 'status': 1, 'result': ['extranonce', bytes(8).hex()]})
        self.job = self.session.consume(self.message)

    def test_latest_mailbox_replaces_pending_and_discards_inflight(self):
        entered = threading.Event(); release = threading.Event(); done = threading.Event()
        results = []; calls = []; stop = threading.Event()
        def process(job, current):
            calls.append(job)
            if job is self.job:
                entered.set()
                if not release.wait(3): raise RuntimeError('test release timeout')
            return job.generation
        def result(job, value):
            results.append((job, value)); stop.set(); done.set()
        worker = LatestJobWorker(self.session, process, result, stop=stop).start()
        try:
            self.assertTrue(worker.publish(self.job)); self.assertTrue(entered.wait(3))
            second = self.session.consume(self.message); worker.publish(second)
            third = self.session.consume(self.message); worker.publish(third)
            release.set(); self.assertTrue(done.wait(3))
        finally:
            release.set(); worker.close()
        self.assertEqual(calls, [self.job, third])
        self.assertEqual(results, [(third, third.generation)])
        self.assertEqual(worker.stats(), {'started': 2, 'completed': 1, 'discarded': 1,
                                         'queued_replacements': 1, 'joined': True})
        self.assertFalse(worker.publish(third))

    def test_close_cancels_current_and_joins_after_stage_returns(self):
        entered = threading.Event(); release = threading.Event(); joined = threading.Event()
        current_seen = []; results = []
        def process(job, current):
            entered.set()
            if not release.wait(3): raise RuntimeError('test release timeout')
            current_seen.append(current(job))
            raise StaleWork('controlled cancellation')
        worker = LatestJobWorker(self.session, process, lambda *a: results.append(a)).start()
        closer = threading.Thread(target=lambda: (worker.close(), joined.set()))
        try:
            worker.publish(self.job); self.assertTrue(entered.wait(3)); closer.start()
            self.assertTrue(worker.closing.wait(3)); self.assertFalse(worker.current(self.job))
            self.assertFalse(joined.is_set()); release.set(); self.assertTrue(joined.wait(3))
        finally:
            release.set()
            if closer.ident is not None: closer.join()
            worker.close()
        self.assertEqual(current_seen, [False]); self.assertEqual(results, [])
        self.assertTrue(worker.stats()['joined'])

    def test_error_propagates_and_stops_receiver(self):
        stop = threading.Event(); results = []
        def fail(job, current): raise RuntimeError('controlled search failure')
        worker = LatestJobWorker(self.session, fail, lambda *a: results.append(a), stop=stop).start()
        try:
            worker.publish(self.job); self.assertTrue(stop.wait(3))
        finally: worker.close()
        self.assertIsInstance(worker.error, RuntimeError); self.assertEqual(results, [])
        self.assertEqual(worker.stats()['completed'], 0)

    def test_receiver_handles_new_job_while_search_is_blocked(self):
        entered = threading.Event(); release = threading.Event(); done = threading.Event()
        stop = threading.Event(); jobs = []; results = []; calls = []
        def process(job, current):
            calls.append(job)
            if len(calls) == 1:
                entered.set()
                if not release.wait(3): raise RuntimeError('test release timeout')
            return job.generation
        def result(job, value):
            results.append(job); stop.set(); done.set()
        worker = LatestJobWorker(self.session, process, result, stop=stop).start()
        def publish(job):
            jobs.append(job); worker.publish(job)
            if len(jobs) == 2: release.set()
        message = self.message
        class Socket:
            count = 0
            sent = []
            closed = False
            def __enter__(stream): return stream
            def __exit__(stream, *args): stream.closed = True
            def sendall(stream, data): stream.sent.append(data)
            def settimeout(stream, value): pass
            def recv(stream, size):
                stream.count += 1
                if stream.count == 1:
                    return b''.join(encode(x, 30+i) for i,x in enumerate([
                        {'id': 0, 'status': 1, 'result': True},
                        {'id': -1, 'status': 1, 'result': ['extranonce', bytes(8).hex()]}, message]))
                if stream.count == 2:
                    if not entered.wait(3): raise RuntimeError('worker did not start')
                    return encode(message, 40)
                if not done.wait(3): raise RuntimeError('latest job did not finish')
                raise TimeoutError('controlled read wakeup')
        stream = Socket()
        try:
            result = PoolReceiver(self.session, 'synthetic.example', 9000, 'synthetic-wallet',
                                  'synthetic-worker', connect=lambda *a, **k: stream).run(
                                      publish, stop=stop, seconds=180)
        finally:
            release.set(); worker.close()
        self.assertEqual(result.jobs, 2); self.assertEqual(len(stream.sent), 1)
        self.assertEqual(results, [jobs[1]]); self.assertEqual(calls, jobs)
        self.assertEqual(worker.stats()['discarded'], 1)
        self.assertTrue(stream.closed); self.assertIsNone(self.session.snapshot())
        self.assertIsNone(worker.error)

    def test_settings_limit_and_worker_start_lifecycle(self):
        worker = LatestJobWorker(self.session, lambda *a: None, lambda *a: None)
        self.assertFalse(worker.publish(self.job))
        worker.close()
        with self.assertRaises(ValueError): worker.start()
        def unexpected(*a, **k): self.fail('invalid setting opened network')
        receiver = PoolReceiver(self.session, 'example', 9000, 'wallet', 'worker', connect=unexpected)
        for seconds in (0, 301):
            with self.assertRaises(ValueError): receiver.run(lambda job: None, seconds=seconds)


if __name__ == '__main__': unittest.main()
