"""Explicit V3 dense profile and generation-gated pool job state. ISC.

No socket, GPU launch or submission. The caller supplies the mining profile and
certificate version; notify metadata/token remain opaque. Assigned extranonce
is retained without assuming its role in a future compact submit.
"""
from dataclasses import dataclass
import struct
import threading

from pool.job import Notify, hex_bytes
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern

MAX_U256 = (1 << 256) - 1
MAX_GENERATION = (1 << 64) - 1


@dataclass(frozen=True)
class MiningProfile:
    m: int
    n: int
    k: int
    rank: int
    rows: PeriodicPattern
    cols: PeriodicPattern

    def __post_init__(self):
        # Deliberately narrow current implementation: V3 dense, rank128,
        # constant bias64/tail1, complete chunk rows, virtual table cap64MiB.
        # Pinned upstream sanity_checks.rs: 82e6eee7076aafe10123e08db78f100d270c0582.
        if (any(type(v) is not int for v in (self.m, self.n, self.k, self.rank))
                or self.rank != 128 or not 2048 <= self.k <= 65536 or self.k % 1024
                or any(not 1 <= dim <= 1 << 24 or dim*self.k > 8*1024**3
                       for dim in (self.m, self.n))
                or not isinstance(self.rows, PeriodicPattern)
                or not isinstance(self.cols, PeriodicPattern)):
            raise ValueError('unsupported explicit dense rank128 profile')
        h, w = self.rows.size, self.cols.size
        if (not 1 <= h <= 32 or not 1 <= w <= 32 or h % 2 or w % 2
                or not 32 <= h*w <= 256 or (h+w)*self.k > 1 << 22
                or self.rows.to_list()[-1] >= self.m or self.cols.to_list()[-1] >= self.n
                or (self.m+self.n)*self.rank + 8*self.k + 16 > 64*1024**2):
            raise ValueError('unsupported pattern dimensions or resource cap')

    @property
    def config(self):
        return struct.pack('<IHH', self.k, self.rank, 0) + self.rows.encoded + self.cols.encoded + bytes(32)

    def share_bound(self, target_bytes):
        if type(target_bytes) is not bytes or len(target_bytes) != 32:
            raise ValueError('expected 32-byte little-endian share target')
        target = int.from_bytes(target_bytes, 'little')
        factor = self.rows.size*self.cols.size*(self.k//self.rank)*128
        # Upstream penalized_target_bound rejects overflow for mining shares;
        # do not use the saturating consensus-nBits helper here.
        if target == 0 or target > MAX_U256//factor:
            raise ValueError('zero or overflowing scaled share target')
        return target*factor


@dataclass(frozen=True)
class PoolJob:
    generation: int
    header: bytes
    job_key: bytes
    share_bound: int
    profile: MiningProfile
    cert_version: int
    target_bytes: bytes
    opaque_metadata: bytes
    opaque_token: bytes
    assigned_extranonce: bytes


class PoolSession:
    """Synchronous job state usable by a future listener/worker pair.

    Publication requires accepted login, a valid assigned extranonce and notify.
    Every notify/extranonce update invalidates prior generation handles. Snapshot
    checks do not provide an atomic network send gate; no submit path exists here.
    """
    def __init__(self, profile, *, cert_version):
        if not isinstance(profile, MiningProfile) or type(cert_version) is not int or cert_version != 3:
            raise ValueError('explicit supported profile and cert_version=3 required')
        self.profile = profile
        self.cert_version = cert_version
        self.generation = 0
        self.accepted = False
        self.extranonce = None
        self.pending = None
        self.active = None
        self.closed = False
        self.lock = threading.RLock()

    def _invalidate(self):
        self.active = None
        if self.generation == MAX_GENERATION:
            self.closed = True
            self.pending = None
            raise ValueError('session generation exhausted')
        self.generation += 1

    def _publish(self):
        if self.accepted and self.extranonce is not None and self.pending is not None and not self.closed:
            notify = self.pending
            header = notify.header
            self.active = PoolJob(self.generation, header, small_hash(header+self.profile.config),
                                  self.profile.share_bound(notify.target_bytes), self.profile,
                                  self.cert_version, notify.target_bytes, notify.payload[76:],
                                  notify.token, self.extranonce)
        return self.active

    def consume(self, message):
        with self.lock:
            if self.closed:
                raise ValueError('pool session is closed')
            if not isinstance(message, dict):
                self._invalidate()
                self.pending = None
                raise ValueError('expected decoded pool message object')
            if type(message.get('id')) is int and message['id'] == 0:
                if message.get('status') != 1 or message.get('result') is not True:
                    self._invalidate()
                    self.pending = self.extranonce = None
                    self.accepted = False
                    self.closed = True
                    raise ValueError('pool login was not accepted')
                if self.accepted:
                    return self.active
                self.accepted = True
                return self._publish()
            result = message.get('result')
            kind = result[0] if isinstance(result, list) and result else None
            if kind == 'extranonce':
                self._invalidate()
                self.extranonce = None
                if (message.get('status') != 1 or len(result) != 2
                        or type(message.get('id')) is not int or message['id'] != -1):
                    self.pending = None
                    raise ValueError('unsupported assigned-extranonce schema')
                self.extranonce = hex_bytes(result[1], 8)
                return self._publish()
            if kind == 'notify':
                self._invalidate()
                self.pending = None
                notify = Notify.parse(message)
                if notify.version_marker != '3':
                    raise ValueError('notify marker differs from explicitly configured V3 policy')
                self.profile.share_bound(notify.target_bytes)
                self.pending = notify
                return self._publish()
            if type(message.get('id')) is int and message['id'] == -1:
                self._invalidate()
                self.pending = None
                raise ValueError('unsupported pool notification')
            return self.active

    def snapshot(self):
        with self.lock:
            return self.active

    def is_current(self, job):
        with self.lock:
            return job is not None and job is self.active and not self.closed and job.generation == self.generation

    def reset(self):
        with self.lock:
            self._invalidate()
            self.accepted = False
            self.extranonce = self.pending = None
            self.closed = False

    def close(self):
        with self.lock:
            self._invalidate()
            self.accepted = False
            self.extranonce = self.pending = None
            self.closed = True
