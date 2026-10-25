"""Bounded pool job receiver over the independent Pearlhash framing. ISC.

One explicit endpoint and login. Optional same-connection gate; no reconnect.
Callbacks must be quick: LatestJobWorker supplies a separate search thread.
Connection end always invalidates the session's active work.
"""
from dataclasses import dataclass
import socket
import threading
import time

from pool.session import PoolSession
from tools.pool_probe import MAX_LINE, decode, encode


class FrameBuffer:
    def __init__(self):
        self.pending = bytearray()

    def feed(self, chunk):
        if type(chunk) is not bytes or len(chunk) > 2*MAX_LINE:
            raise ValueError('invalid bounded pool read')
        self.pending.extend(chunk)
        messages = []
        while True:
            end = self.pending.find(b'\n')
            if end < 0:
                if len(self.pending) >= MAX_LINE:
                    raise ValueError('oversized unfinished pool frame')
                return messages
            if end + 1 > MAX_LINE:
                raise ValueError('oversized pool frame')
            line = bytes(self.pending[:end+1])
            del self.pending[:end+1]
            messages.append(decode(line))

    def eof(self):
        if self.pending:
            raise ValueError('pool connection ended with a truncated frame')


@dataclass(frozen=True)
class ReceiveResult:
    messages: int
    jobs: int
    bytes_received: int
    stop_reason: str


class PoolReceiver:
    def __init__(self, session, host, port, wallet, worker, *,
                 connect=socket.create_connection, clock=time.monotonic,
                 agent='pearlhash-independent/0.0.30'):
        if not isinstance(session, PoolSession):
            raise ValueError('expected configured pool session')
        if (type(host) is not str or not host or len(host) > 253
                or type(port) is not int or not 1 <= port <= 65535
                or type(wallet) is not str or not 1 <= len(wallet) <= 256
                or type(worker) is not str or not 1 <= len(worker) <= 64):
            raise ValueError('invalid explicit pool endpoint or login fields')
        if type(agent)is not str or not 1<=len(agent)<=96:
            raise ValueError('bounded truthful agent name required')
        self.agent=agent
        self.session = session
        self.endpoint = (host, port)
        self.wallet = wallet
        self.worker = worker
        self.connect = connect
        self.clock = clock

    def run(self, on_job, *, stop=None, seconds=30, max_messages=64, gate=None, on_response=None):
        if (type(seconds) is not int or not 1 <= seconds <= 300
                or type(max_messages) is not int or not 1 <= max_messages <= 256
                or not callable(on_job)):
            raise ValueError('invalid bounded receiver settings')
        if gate is not None and gate.session is not self.session:
            raise ValueError('gate belongs to a different session')
        stop = stop if stop is not None else threading.Event()
        self.session.reset()
        messages = jobs = received = 0
        last_job = None
        deadline = self.clock() + seconds
        try:
            if stop.is_set():
                return ReceiveResult(0, 0, 0, 'requested')
            # Only this explicit endpoint is dialed. The public framing encoder
            # supplies a fresh transport nonce, never a mining/share nonce.
            from contextlib import ExitStack
            with ExitStack() as lifetime:
                stream=lifetime.enter_context(self.connect(self.endpoint, timeout=min(10, seconds)))
                if gate is not None:lifetime.callback(gate.detach)
                stream.sendall(encode({'id': 0, 'method': 'login',
                                      'params': [self.wallet, self.worker, self.agent]}))
                stream.settimeout(0.5)
                if gate is not None:gate.attach(stream)
                frames = FrameBuffer()
                while not stop.is_set():
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        return ReceiveResult(messages, jobs, received, 'deadline')
                    stream.settimeout(min(0.5, remaining))
                    try:
                        chunk = stream.recv(4096)
                    except TimeoutError:
                        continue
                    if not chunk:
                        frames.eof()
                        return ReceiveResult(messages, jobs, received, 'eof')
                    received += len(chunk)
                    if received > 1024**2:
                        raise ValueError('pool receive byte budget exceeded')
                    for message in frames.feed(chunk):
                        if stop.is_set():
                            break
                        if messages >= max_messages:
                            raise ValueError('pool message budget exceeded')
                        messages += 1
                        if gate is not None:
                            verdict=gate.response(message)
                            if verdict is not None and on_response is not None:on_response(verdict)
                            if self.session.closed:raise ConnectionError('connection gate closed')
                        job = self.session.consume(message)
                        if job is not None and job is not last_job:
                            if not self.session.is_current(job):
                                raise ValueError('pool job became stale before callback')
                            jobs += 1
                            last_job = job
                            on_job(job)
                return ReceiveResult(messages, jobs, received, 'requested')
        finally:
            self.session.close()
