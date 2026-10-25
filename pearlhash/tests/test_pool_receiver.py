"""Stream fragmentation, one-endpoint login and receiver lifetime checks. ISC."""
import threading
import unittest

from pool.receiver import FrameBuffer, PoolReceiver
from pool.session import MiningProfile, PoolSession
from reference.patterns import PeriodicPattern
from tools.pool_probe import MAX_LINE, decode, encode


def session():
    pattern = PeriodicPattern.from_list([0, 1, 8, 9, 64, 65, 72, 73])
    return PoolSession(MiningProfile(128, 128, 4096, 128, pattern, pattern), cert_version=3)


LOGIN = {'id': 0, 'status': 1, 'result': True}
EXTRA = {'id': -1, 'status': 1, 'result': ['extranonce', bytes(8).hex()]}
NOTIFY = {'id': -1, 'status': 1, 'result': ['notify', bytes(200).hex(),
          (1 << 200).to_bytes(32, 'little').hex(), bytes(8).hex(), '3']}


class Socket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.sent = []
        self.closed = False
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def sendall(self, data): self.sent.append(data)
    def settimeout(self, value): pass
    def recv(self, size): return next(self.chunks, b'')


class ReceiverTests(unittest.TestCase):
    def test_fragmented_and_coalesced_frames(self):
        frames = [LOGIN, EXTRA, NOTIFY]
        wire = b''.join(encode(frame, 20+i) for i, frame in enumerate(frames))
        reader = FrameBuffer()
        decoded = []
        for start in range(0, len(wire), 7): decoded.extend(reader.feed(wire[start:start+7]))
        self.assertEqual(decoded, frames)
        reader.eof()
        self.assertEqual(FrameBuffer().feed(wire), frames)
        with self.assertRaises(ValueError): FrameBuffer().feed(b'0'*MAX_LINE)
        partial = FrameBuffer(); partial.feed(wire[:9])
        with self.assertRaises(ValueError): partial.eof()

    def test_one_endpoint_login_and_disconnect_invalidation(self):
        stream = Socket([encode(LOGIN, 20), encode(EXTRA, 21)+encode(NOTIFY, 22)])
        calls = []
        state = session()
        def connect(endpoint, *, timeout):
            calls.append(endpoint)
            return stream
        jobs = []
        def callback(job):
            self.assertTrue(state.is_current(job))
            jobs.append(job)
        result = PoolReceiver(state, 'configured.example', 9000, 'synthetic-wallet', 'synthetic-worker',
                              connect=connect).run(callback)
        self.assertEqual(calls, [('configured.example', 9000)])
        self.assertEqual(len(stream.sent), 1)
        request = decode(stream.sent[0])
        self.assertEqual(request['method'], 'login')
        self.assertEqual(request['params'][:2], ['synthetic-wallet', 'synthetic-worker'])
        self.assertEqual((result.messages, result.jobs, result.stop_reason), (3, 1, 'eof'))
        self.assertTrue(stream.closed)
        self.assertFalse(state.is_current(jobs[0]))
        self.assertIsNone(state.snapshot())

    def test_job_updates_callback_failure_and_cancel(self):
        messages = [LOGIN, EXTRA, NOTIFY, NOTIFY]
        stream = Socket([b''.join(encode(m, 20+i) for i, m in enumerate(messages))])
        state = session(); jobs = []
        def callback(job):
            if jobs: self.assertFalse(state.is_current(jobs[-1]))
            jobs.append(job)
        result = PoolReceiver(state, 'example', 9000, 'wallet', 'worker', connect=lambda *a, **k: stream).run(callback)
        self.assertEqual(result.jobs, 2)
        self.assertGreater(jobs[1].generation, jobs[0].generation)
        failing = Socket([b''.join(encode(m, 20+i) for i, m in enumerate(messages[:3]))])
        def fail(job): raise RuntimeError('controlled callback failure')
        with self.assertRaises(RuntimeError):
            PoolReceiver(state, 'example', 9000, 'wallet', 'worker', connect=lambda *a, **k: failing).run(fail)
        self.assertTrue(failing.closed); self.assertIsNone(state.snapshot())
        stop = threading.Event(); stop.set()
        def unexpected(*args, **kwargs): self.fail('cancelled receiver connected')
        result = PoolReceiver(state, 'example', 9000, 'wallet', 'worker', connect=unexpected).run(jobs.append, stop=stop)
        self.assertEqual(result.stop_reason, 'requested')

    def test_truncated_invalid_and_budget_failures_close_work(self):
        for tail in (b'abc', b'not-hex\n'):
            state = session()
            stream = Socket([encode(LOGIN, 20)+encode(EXTRA, 21)+encode(NOTIFY, 22), tail])
            jobs = []
            with self.assertRaises(ValueError):
                PoolReceiver(state, 'example', 9000, 'wallet', 'worker', connect=lambda *a, **k: stream).run(jobs.append)
            self.assertTrue(stream.closed)
            self.assertFalse(state.is_current(jobs[0]))
        state = session()
        stream = Socket([encode(LOGIN, 20)+encode(EXTRA, 21)])
        with self.assertRaises(ValueError):
            PoolReceiver(state, 'example', 9000, 'wallet', 'worker', connect=lambda *a, **k: stream).run(lambda job: None, max_messages=1)
        self.assertTrue(stream.closed)

    def test_timeout_deadline_closes_without_a_job(self):
        class TimeoutSocket(Socket):
            def recv(self, size): raise TimeoutError('controlled read timeout')
        stream = TimeoutSocket([])
        times = iter((0, 0, 1))
        state = session()
        result = PoolReceiver(state, 'example', 9000, 'wallet', 'worker',
                              connect=lambda *a, **k: stream, clock=lambda: next(times)).run(
                                  lambda job: self.fail('unexpected job'), seconds=1)
        self.assertEqual((result.jobs, result.stop_reason), (0, 'deadline'))
        self.assertTrue(stream.closed)
        self.assertIsNone(state.snapshot())


if __name__ == '__main__':
    unittest.main()
