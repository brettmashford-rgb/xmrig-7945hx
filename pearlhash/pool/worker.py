"""Single search thread with a one-slot latest-job mailbox. ISC.

The receiver remains responsive while native/GPU stages execute. GPU context
creation/use/destruction belongs inside process(), on this worker thread. Native
commitment calls cannot abort mid-call; close waits for that call to return.
No network send or submit gate is implemented here.
"""
import threading

from pool.search import StaleWork
from pool.session import PoolSession


class LatestJobWorker:
    def __init__(self, session, process, on_result, *, stop=None):
        if not isinstance(session, PoolSession) or not callable(process) or not callable(on_result):
            raise ValueError('configured session and worker callbacks required')
        self.session = session
        self.process = process
        self.on_result = on_result
        self.stop = stop if stop is not None else threading.Event()
        self.closing = threading.Event()
        self.condition = threading.Condition()
        self.pending = None
        self.error = None
        self.started = self.completed = self.discarded = self.replaced = 0
        self.thread = None

    def current(self, job):
        return not self.closing.is_set() and not self.stop.is_set() and self.session.is_current(job)

    def start(self):
        with self.condition:
            if self.thread is not None or self.closing.is_set():
                raise ValueError('worker can only start once')
            self.thread = threading.Thread(target=self._run, name='pearlhash-search', daemon=False)
            self.thread.start()
        return self

    def publish(self, job):
        # No native work or GPU launch in the receiver callback.
        if not self.current(job):
            return False
        with self.condition:
            if self.thread is None or self.closing.is_set() or self.stop.is_set():
                return False
            if self.pending is not None:
                self.replaced += 1
            self.pending = job
            self.condition.notify()
            return True

    def _run(self):
        while not self.closing.is_set() and not self.stop.is_set():
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.closing.is_set()
                                        or self.stop.is_set(), timeout=0.25)
                if self.closing.is_set() or self.stop.is_set():
                    break
                job, self.pending = self.pending, None
            if job is None:
                continue
            try:
                if not self.current(job):
                    raise StaleWork('queued job was replaced')
                with self.condition:
                    self.started += 1
                result = self.process(job, self.current)
                # Serialize current-job observation/result callback with session
                # replacement. Callback must be quick and must not send shares.
                with self.session.lock:
                    if not self.current(job):
                        raise StaleWork('completed worker result became stale')
                    self.on_result(job, result)
                    with self.condition:
                        self.completed += 1
            except StaleWork:
                with self.condition:
                    self.discarded += 1
            except Exception as error:
                with self.condition:
                    self.error = error
                self.stop.set()
                break
        with self.condition:
            self.pending = None

    def stats(self):
        with self.condition:
            return {'started': self.started, 'completed': self.completed,
                    'discarded': self.discarded, 'queued_replacements': self.replaced,
                    'joined': self.thread is not None and not self.thread.is_alive()}

    def close(self):
        self.closing.set()
        with self.condition:
            self.pending = None
            self.condition.notify_all()
        if self.thread is not None:
            if threading.current_thread() is self.thread:
                raise RuntimeError('worker cannot join itself')
            self.thread.join()
