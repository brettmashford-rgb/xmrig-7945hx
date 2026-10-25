"""Job-driven nonce preparation/search/proofs; no socket or submission. ISC.

Worker nonce is an explicit caller input. This module does not infer its mapping
from assigned extranonce. Native commitment calls finish before checking stale
state; cancellation prevents subsequent stages, not an in-progress native call.
"""
from dataclasses import dataclass

from pool.session import PoolJob
from reference.constant_merkle import constant_opening
from reference.patterns import PeriodicPattern
from reference.plain_proof import PlainProof
from reference.pool_nonce import nonce_tail
from reference.seeds import dense_noise_seeds
from reference.tile_ranges import PatternDomain, RangeBatch, RangeCursor, run_range
from tools.candidate_scan import CandidateBackend
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import TileQuery, query_reference
from tools.global_range import GlobalRangePlan


class StaleWork(RuntimeError):
    pass


def require_current(job, current):
    if not isinstance(job, PoolJob) or not current(job):
        raise StaleWork('job is no longer current')


def plan_for(job):
    p = job.profile
    return GlobalRangePlan(PatternDomain(p.m, p.rows), PatternDomain(p.n, p.cols))


@dataclass(frozen=True)
class Base:
    job_key: bytes
    n: int
    k: int
    opening: object


@dataclass(frozen=True)
class Nonce:
    job: PoolJob
    worker: bytes
    miner: bytes
    base: Base
    root_a: bytes
    profile: ConstantProfile


@dataclass(frozen=True)
class Hit:
    generation: int
    tile: int
    digest: bytes


def prepare_base(job, current):
    require_current(job, current)
    p = job.profile
    opening = constant_opening(job.job_key, 64, p.n*p.k//1024, [0], p.k)
    require_current(job, current)
    return Base(job.job_key, p.n, p.k, opening)


def prepare_nonce(job, base, worker, miner, current):
    require_current(job, current)
    if any(type(v) is not bytes or len(v) != 8 for v in (worker, miner)):
        raise ValueError('explicit eight-byte worker and miner nonces required')
    p = job.profile
    if (not isinstance(base, Base) or (base.job_key, base.n, base.k) != (job.job_key, p.n, p.k)
            or base.opening.total_leaves != p.n*p.k//1024 or base.opening.rows != [0]):
        raise ValueError('base commitment belongs to a different job/profile')
    base.opening.verify(job.job_key)
    tail = nonce_tail(worker, miner)
    opening = constant_opening(job.job_key, 64, p.m*p.k//1024, [0], p.k, tail=tail)
    require_current(job, current)
    bs, ass = dense_noise_seeds(job.job_key, opening.root, base.opening.root,
                               p.m, p.n, cert_version=job.cert_version)
    profile = ConstantProfile(p.m, p.n, p.k, p.rank, 64, tail, ass, bs)
    return Nonce(job, worker, miner, base, opening.root, profile)


class NonceSearch:
    """Resumable windows over one nonce; owns one backend/cache until close.

    The CUDA context belongs to the caller. This object closes only its own
    nonce cache. Window boundaries retain the committed global tile cursor;
    stale jobs or dispatch failures close the cache and cannot resume it.
    """
    def __init__(self, context, device, current, *, start=0, backend_factory=CandidateBackend):
        self.context = context
        self.job = context.job
        self.current = current
        self.plan = plan_for(self.job)
        self.hit = None
        self.closed = False
        self.backend = None
        require_current(self.job, current)
        if type(start) is not int or not 0 <= start <= self.plan.count:
            raise ValueError('invalid search start')
        self.cursor = RangeCursor(self.job.generation, start, start)
        try:
            self.backend = backend_factory(context.profile, device, bound=self.job.share_bound)
            require_current(self.job, current)
        except BaseException:
            self.close()
            raise

    def advance(self, tiles):
        if self.closed:
            raise ValueError('nonce search is closed')
        if type(tiles) is not int or tiles < 0:
            raise ValueError('invalid search window size')
        if self.hit is not None:
            raise ValueError('nonce search already found a candidate')
        try:
            require_current(self.job, self.current)
            self.cursor.stop = min(self.plan.count, self.cursor.next_tile + tiles)
            def generation():
                return self.job.generation if self.hit is None and self.current(self.job) else self.job.generation ^ 1
            def deliver(records):
                require_current(self.job, self.current)
                if records and self.hit is None:
                    tile, digest, gen = records[0]
                    self.hit = Hit(gen, tile, digest)
            run_range(self.plan, self.cursor, self.backend, generation, deliver)
            require_current(self.job, self.current)
            return self.hit, self.cursor
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            if self.backend is not None:
                self.backend.close()

    def __enter__(self):
        if self.closed:
            raise ValueError('nonce search is closed')
        return self

    def __exit__(self, *args):
        self.close()


def search_nonce(context, device, current, *, start=0, stop=None, backend_factory=CandidateBackend):
    require_current(context.job, current)
    total = plan_for(context.job).count
    stop = total if stop is None else stop
    if any(type(v) is not int for v in (start, stop)) or not 0 <= start <= stop <= total:
        raise ValueError('invalid search window')
    with NonceSearch(context, device, current, start=start, backend_factory=backend_factory) as search:
        return search.advance(stop-start)


def build_proof(context, hit, current):
    job = context.job
    require_current(job, current)
    p = job.profile
    if (not isinstance(hit, Hit) or hit.generation != job.generation
            or type(hit.digest) is not bytes or len(hit.digest) != 32
            or int.from_bytes(hit.digest, 'little') > job.share_bound):
        raise ValueError('stale or target-failing candidate')
    rows, cols = plan_for(job).indices(hit.tile)
    batch = RangeBatch(hit.tile, hit.tile+1, rows, cols,
                       ((tuple(range(len(rows))), tuple(range(len(cols)))),))
    matrix = context.profile.case(batch).matrix()
    words, digest = query_reference(matrix, [TileQuery(*batch.maps[0])])[0]
    if digest != hit.digest or nonce_tail(context.worker, context.miner) != context.profile.tail:
        raise ValueError('candidate digest or nonce binding differs')
    require_current(job, current)
    a = constant_opening(job.job_key, 64, p.m*p.k//1024, list(rows), p.k, tail=context.profile.tail)
    require_current(job, current)
    b = constant_opening(job.job_key, 64, p.n*p.k//1024, list(cols), p.k)
    require_current(job, current)
    if a.root != context.root_a or b.root != context.base.opening.root:
        raise ValueError('candidate commitment roots differ')
    bs, ass = dense_noise_seeds(job.job_key, a.root, b.root, p.m, p.n, cert_version=job.cert_version)
    if (ass, bs) != (context.profile.seed_a, context.profile.seed_b):
        raise ValueError('candidate noise seeds differ')
    for indices, pattern in ((rows, p.rows), (cols, p.cols)):
        if PeriodicPattern.from_list([v-indices[0] for v in indices]) != pattern:
            raise ValueError('candidate pattern differs')
    raw = PlainProof(p.m, p.n, p.k, p.rank, a, b).serialize()
    parsed = PlainProof.parse(raw)
    if parsed.serialize() != raw:
        raise ValueError('proof encoding round-trip differs')
    parsed.a.verify(job.job_key)
    parsed.bt.verify(job.job_key)
    require_current(job, current)
    return raw, words
