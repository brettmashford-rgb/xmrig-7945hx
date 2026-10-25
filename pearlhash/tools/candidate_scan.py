"""GPU tile search with CPU recomputation of returned candidates only. ISC.

Misses are not recomputed by this search path. The separate correctness harness
compares complete hit sets with CPU references; this module cannot independently
detect GPU false negatives. No pool IO or consensus/version inference occurs.
"""
import ctypes as C
import struct

from tools.check_tile_scan_gpu import MAX_BOUND, ScanResult, validate_scan
from tools.global_range import GlobalBatch, GlobalRangePlan
from tools.virtual_scan import VirtualScanner, VirtualTables, global_reference, pack_global_queries, table_payload


def decode_queue(raw, status, bounds, capacity, generation):
    """Validate wire structure without computing unreturned tile digests."""
    validate_scan(bounds, capacity, generation)
    if len(raw) != capacity * 44 or len(status) != 8:
        raise ValueError('candidate queue/status length differs')
    total, overflow = struct.unpack('<2I', status)
    if total > len(bounds) or overflow != int(total > capacity):
        raise ValueError('invalid candidate count or overflow flag')
    records = {}
    for index in range(min(total, capacity)):
        offset = index * 44
        tile, lo, hi = struct.unpack_from('<3I', raw, offset)
        digest = raw[offset + 12:offset + 44]
        if (tile >= len(bounds) or tile in records or (lo | (hi << 32)) != generation
                or int.from_bytes(digest, 'little') > bounds[tile]):
            raise ValueError('unknown, duplicate, stale or target-failing candidate')
        records[tile] = digest
    return ScanResult(total, bool(overflow), records)


def verify_returned(result, queries, reference_for):
    """Partial queues must retry; a complete queue verifies only its hits."""
    if result.overflow:
        return 0
    if result.total != len(result.records):
        raise ValueError('complete candidate count differs')
    for tile, digest in result.records.items():
        if reference_for(queries[tile]) != digest:
            raise ValueError('candidate digest differs from independent CPU math')
    return result.total


class CandidateScanner(VirtualScanner):
    def __init__(self):
        super().__init__()
        self.verified_tiles = 0
        self.dispatches = 0

    def scan_candidates(self, tables, queries, bounds, capacity, generation):
        if tables.device is not self or tables.closed:
            raise ValueError('foreign or closed candidate cache')
        profile = tables.profile
        descriptors = pack_global_queries(profile, queries)
        validate_scan(bounds, capacity, generation)
        if len(bounds) != len(queries):
            raise ValueError('candidate target/query count differs')
        mark = len(self.allocations)
        try:
            desc = self.allocate(descriptors)
            limits = self.allocate(b''.join(bound.to_bytes(32, 'little') for bound in bounds))
            status, s = self.guarded(8)
            zero = C.create_string_buffer(bytes(8), 8)
            self.api('cuMemcpyHtoD_v2', [C.c_ulonglong, C.c_void_p, C.c_size_t], s, zero, 8)
            queue, q = self.guarded(capacity * 44)
            trace, t = self.guarded(0)
            arguments = (*tables.inputs(), desc, limits, tables.key_a, s, q, t,
                         C.c_uint(0), C.c_uint(capacity), C.c_uint(len(queries)),
                         C.c_uint(profile.m), C.c_uint(profile.n), C.c_uint(profile.k),
                         C.c_uint(profile.rank), C.c_int(profile.fill), C.c_ulonglong(generation))
            self.launch(b'virtual_tile_scan', arguments, len(queries), 256)
            self.dispatches += 1
            self.api('cuCtxSynchronize', [])
            result = decode_queue(self.checked_download(queue, capacity * 44),
                                  self.checked_download(status, 8), bounds, capacity, generation)
            self.checked_download(trace, 0)
            tables.check_guards()
            self.verified_tiles += verify_returned(
                result, queries, lambda query: global_reference(profile, (query,))[0][1])
            return result
        finally:
            for pointer in reversed(self.allocations[mark:]):
                self.release(pointer)


class CandidateBackend:
    """One nonce cache; candidate-only CPU validation; bounded global batches."""
    def __init__(self, profile, device=None, *, bound=MAX_BOUND):
        table_payload(profile)
        validate_scan([bound], 1, 0)
        self.profile = profile
        self.device = device
        self.bound = bound
        self.tables = VirtualTables(device, profile) if device is not None else None
        self.closed = False

    def __call__(self, batch, capacity, generation):
        if self.closed or not isinstance(batch, GlobalBatch):
            raise ValueError('expected open candidate backend and global batch')
        queries = batch.queries()
        bounds = [self.bound] * len(queries)
        validate_scan(bounds, capacity, generation)
        if self.device is not None:
            return self.device.scan_candidates(self.tables, queries, bounds, capacity, generation)
        # Explicit CPU emulation for development only: it must compute misses
        # to emulate a GPU. Never report this branch as candidate-only GPU work.
        references = global_reference(self.profile, queries)
        hits = {i: digest for i, (_, digest) in enumerate(references)
                if int.from_bytes(digest, 'little') <= self.bound}
        return ScanResult(len(hits), len(hits) > capacity, dict(list(hits.items())[:capacity]))

    def close(self):
        if not self.closed:
            if self.tables is not None:
                self.tables.close()
            self.closed = True


def find_nonce_candidate(context, device=None):
    """Fresh synthetic nonce search, preserving global IDs for proof binding."""
    from reference.tile_ranges import RangeCursor, run_range
    from tools.offline_nonce_search import BOUND, FoundTile

    original = context.job.plan()
    plan = GlobalRangePlan(original.a, original.b)
    cursor = RangeCursor(context.generation, 0, plan.count)
    current = [context.generation]
    found = []
    def deliver(records):
        if records and not found:
            tile, digest, generation = records[0]
            found.append(FoundTile(generation, tile, digest))
            current[0] = context.generation ^ 1
    backend = CandidateBackend(context.profile, device, bound=BOUND)
    try:
        run_range(plan, cursor, backend, lambda: current[0], deliver)
    finally:
        backend.close()
    return (found[0] if found else None), cursor
