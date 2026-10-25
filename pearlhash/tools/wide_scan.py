"""Up to 4096 queries per existing virtual_tile_scan launch. ISC.

Same kernel ABI/PTX and per-tile math; larger bounded descriptor/target/queue
buffers. No CPU recomputation of misses. Returned identical queries share an
independent CPU reference within a dispatch. No pool or submission code.
"""
import ctypes as C
from dataclasses import dataclass
import struct

from reference.tile_ranges import RangePlan, PatternDomain
from tools.candidate_scan import CandidateScanner, verify_returned
from tools.check_tile_scan_gpu import MAX_BOUND, ScanResult, TileQuery
from tools.global_range import GlobalBatch
from tools.virtual_scan import VirtualTables, table_payload, pack_global_queries, global_reference

MAX_QUERIES = 4096


def validate_wide(bounds, capacity, generation):
    if (not 1 <= len(bounds) <= MAX_QUERIES or type(capacity) is not int
            or not 0 <= capacity <= MAX_QUERIES or type(generation) is not int
            or not 0 <= generation < 1 << 64
            or any(type(b) is not int or not 0 <= b <= MAX_BOUND for b in bounds)):
        raise ValueError('invalid wide query/target/queue limits')


def pack_wide(profile, queries):
    if not 1 <= len(queries) <= MAX_QUERIES:
        raise ValueError('expected 1..4096 wide queries')
    # Reuse the established 66-u32 descriptor serializer/row validation.
    return b''.join(pack_global_queries(profile, queries[i:i+64])
                    for i in range(0, len(queries), 64))


def decode_wide(raw, status, bounds, capacity, generation):
    validate_wide(bounds, capacity, generation)
    if len(raw) != capacity*44 or len(status) != 8:
        raise ValueError('wide queue/status size differs')
    total, overflow = struct.unpack('<2I', status)
    if total > len(bounds) or overflow != int(total > capacity):
        raise ValueError('invalid wide queue count/overflow')
    records = {}
    for index in range(min(total, capacity)):
        offset = index*44
        tile, lo, hi = struct.unpack_from('<3I', raw, offset)
        digest = raw[offset+12:offset+44]
        if (tile >= len(bounds) or tile in records or (lo | hi << 32) != generation
                or int.from_bytes(digest, 'little') > bounds[tile]):
            raise ValueError('unknown, duplicate, stale or target-failing wide candidate')
        records[tile] = digest
    return ScanResult(total, bool(overflow), records)


@dataclass(frozen=True)
class WideBatch:
    start: int
    stop: int
    maps: tuple

    def __post_init__(self):
        if (any(type(v) is not int for v in (self.start, self.stop)) or self.start < 0
                or not 1 <= self.stop-self.start <= MAX_QUERIES or type(self.maps) is not tuple
                or len(self.maps) != self.stop-self.start):
            raise ValueError('invalid wide batch interval')
        for i in range(0, len(self.maps), 64):
            chunk = self.maps[i:i+64]
            GlobalBatch(0, len(chunk), chunk)

    def queries(self):
        return tuple(TileQuery(rows, cols) for rows, cols in self.maps)


class WideRangePlan(RangePlan):
    def __init__(self, a, b, *, batch_queries=MAX_QUERIES):
        super().__init__(a, b)
        if type(batch_queries) is not int or not 1 <= batch_queries <= MAX_QUERIES:
            raise ValueError('invalid wide batch query cap')
        self.batch_queries = batch_queries

    def batches(self, start, stop):
        if any(type(v) is not int for v in (start, stop)) or not 0 <= start <= stop <= self.count:
            raise ValueError('invalid wide tile interval')
        for first in range(start, stop, self.batch_queries):
            end = min(first+self.batch_queries, stop)
            yield WideBatch(first, end, tuple(self.indices(tile) for tile in range(first, end)))


def wide_plan_for(job):
    p = job.profile
    return WideRangePlan(PatternDomain(p.m, p.rows), PatternDomain(p.n, p.cols))


class WideCandidateScanner(CandidateScanner):
    def __init__(self):
        super().__init__()
        self.wide_dispatches = 0
        self.unique_cpu_checks = 0

    def scan_wide(self, tables, queries, bounds, capacity, generation):
        if tables.device is not self or tables.closed:
            raise ValueError('foreign or closed wide nonce cache')
        descriptors = pack_wide(tables.profile, queries)
        validate_wide(bounds, capacity, generation)
        if len(queries) != len(bounds):
            raise ValueError('wide query/target counts differ')
        profile = tables.profile
        mark = len(self.allocations)
        try:
            desc = self.allocate(descriptors)
            limits = self.allocate(b''.join(b.to_bytes(32, 'little') for b in bounds))
            status, s = self.guarded(8)
            zero = C.create_string_buffer(bytes(8), 8)
            self.api('cuMemcpyHtoD_v2', [C.c_ulonglong, C.c_void_p, C.c_size_t], s, zero, 8)
            queue, q = self.guarded(capacity*44)
            trace, t = self.guarded(0)
            arguments = (*tables.inputs(), desc, limits, tables.key_a, s, q, t,
                         C.c_uint(0), C.c_uint(capacity), C.c_uint(len(queries)),
                         C.c_uint(profile.m), C.c_uint(profile.n), C.c_uint(profile.k),
                         C.c_uint(profile.rank), C.c_int(profile.fill), C.c_ulonglong(generation))
            self.launch(b'virtual_tile_scan', arguments, len(queries), 256)
            self.dispatches += 1
            self.wide_dispatches += 1
            self.api('cuCtxSynchronize', [])
            result = decode_wide(self.checked_download(queue, capacity*44),
                                 self.checked_download(status, 8), bounds, capacity, generation)
            self.checked_download(trace, 0)
            tables.check_guards()
            references = {}
            def reference(query):
                if query not in references:
                    references[query] = global_reference(profile, (query,))[0][1]
                    self.unique_cpu_checks += 1
                return references[query]
            self.verified_tiles += verify_returned(result, queries, reference)
            return result
        finally:
            for pointer in reversed(self.allocations[mark:]):
                self.release(pointer)


class WideCandidateBackend:
    def __init__(self, profile, device, *, bound=MAX_BOUND):
        table_payload(profile)
        validate_wide([bound], 1, 0)
        if not isinstance(device, WideCandidateScanner):
            raise ValueError('wide GPU scanner required; no CPU emulation fallback')
        self.profile = profile
        self.device = device
        self.bound = bound
        self.closed = False
        self.tables = VirtualTables(device, profile)

    def __call__(self, batch, capacity, generation):
        if self.closed or not isinstance(batch, WideBatch):
            raise ValueError('expected open wide backend and batch')
        return self.device.scan_wide(self.tables, batch.queries(),
                                     [self.bound]*len(batch.maps), capacity, generation)

    def close(self):
        if not self.closed:
            self.tables.close()
            self.closed = True
