"""Global-index range batches for the virtual GPU input path. ISC.

Unlike materialized batches, different queries do not share a 32-row pool.
The kernel is unchanged. Every dispatched tile still has a CPU reference.
"""
from dataclasses import dataclass

from reference.tile_ranges import RangePlan
from tools.check_tile_scan_gpu import MAX_BOUND, ScanResult, TileQuery
from tools.virtual_scan import VirtualTables, global_reference, table_payload


@dataclass(frozen=True)
class GlobalBatch:
    start: int
    stop: int
    maps: tuple

    def __post_init__(self):
        if (any(type(v) is not int for v in (self.start, self.stop))
                or self.start < 0 or not 1 <= self.stop - self.start <= 64
                or type(self.maps) is not tuple
                or len(self.maps) != self.stop - self.start):
            raise ValueError('invalid global batch interval')
        for mapping in self.maps:
            if type(mapping) is not tuple or len(mapping) != 2:
                raise ValueError('invalid global tile mapping')
            for indices in mapping:
                if (type(indices) is not tuple or not 1 <= len(indices) <= 32
                        or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in indices)):
                    raise ValueError('invalid global row/column indices')

    def queries(self):
        return tuple(TileQuery(rows, cols) for rows, cols in self.maps)


class GlobalRangePlan(RangePlan):
    """Bounded, lazy batches of up to 64 global queries, preserving tile IDs."""

    def batches(self, start, stop):
        if (any(type(v) is not int for v in (start, stop))
                or not 0 <= start <= stop <= self.count):
            raise ValueError('invalid global tile interval')
        for first in range(start, stop, self.batch_queries):
            end = min(first + self.batch_queries, stop)
            yield GlobalBatch(first, end, tuple(self.indices(tile) for tile in range(first, end)))


class GlobalRangeBackend:
    """Keep one nonce cache across batches/retries; CPU-check every tile.

    A GlobalBatch is deliberately distinct from a materialized RangeBatch:
    its indices are global, never local pool slots. No live pool IO occurs.
    """

    def __init__(self, profile, device=None, *, bound=MAX_BOUND):
        table_payload(profile)
        if type(bound) is not int or not 0 <= bound <= MAX_BOUND:
            raise ValueError('invalid global range bound')
        self.profile = profile
        self.device = device
        self.bound = bound
        self.batch = None
        self.reference = None
        self.tables = VirtualTables(device, profile) if device is not None else None
        self.launches = 0
        self.reference_batches = 0
        self.closed = False

    def __call__(self, batch, capacity, generation):
        from tools.check_tile_scan_gpu import validate_scan
        from tools.virtual_scan import pack_global_queries

        if self.closed or not isinstance(batch, GlobalBatch):
            raise ValueError('expected an open backend and global batch')
        queries = batch.queries()
        bounds = [self.bound] * len(queries)
        validate_scan(bounds, capacity, generation)
        pack_global_queries(self.profile, queries)
        if batch != self.batch:
            reference = global_reference(self.profile, queries)
            self.reference = reference
            self.batch = batch
            self.reference_batches += 1
        self.launches += 1
        if self.device is None:
            hits = {i: digest for i, (_, digest) in enumerate(self.reference)
                    if int.from_bytes(digest, 'little') <= self.bound}
            return ScanResult(len(hits), len(hits) > capacity,
                              dict(list(hits.items())[:capacity]))
        return self.device.scan_virtual(self.tables, queries, self.reference, bounds,
                                        capacity, generation, audit=True)

    def close(self):
        if not self.closed:
            if self.tables is not None:
                self.tables.close()
            self.batch = self.reference = None
            self.closed = True
