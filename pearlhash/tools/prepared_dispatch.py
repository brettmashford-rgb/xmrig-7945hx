"""Bounded reusable dispatch buffers for validated production kernels. ISC.

Explicit offline backend only; no live miner selects it automatically. A batch
retains global queries for independent CPU candidate checks. Mapping/descriptor
serialization is shared by repeated row/column tuples, not skipped validation.
"""
import ctypes as C
from dataclasses import dataclass
import struct

from tools.check_tile_scan_gpu import TileQuery
from tools.production_scan import require_production
from tools.virtual_scan import table_payload, global_reference
from tools.wide_scan import validate_wide, decode_wide
from tools.candidate_scan import verify_returned

LIMIT = 4096
GUARD = b'\xa5'*16
KERNELS = (b'production_virtual_tile_scan', b'fragment_cached_tile_scan', b'cooperative_tile_scan')


@dataclass(frozen=True)
class PreparedBatch:
    owner: object
    queries: tuple
    descriptors: bytes
    bounds: tuple
    targets: bytes


class QueryPacker:
    def __init__(self, profile, cache=None):
        table_payload(profile); require_production(profile, ())
        self.profile = profile; self.cache = cache
        self.axes = ({}, {})

    def axis(self, values, side):
        if type(values) is not tuple:
            raise ValueError('immutable tuple of global indices required')
        count = (10, 16)[side]; limit = (self.profile.m, self.profile.n)[side]
        try:
            known = self.axes[side].get(values)
        except TypeError:
            raise ValueError('unhashable query index') from None
        # Immutable tuple identity permits reusing validation. For equal but
        # distinct tuples validate types: bool and int compare/hash equally.
        if known is not None and values is known[0]:
            return known[1]
        if len(values) != count or any(type(v) is not int for v in values):
            raise ValueError('invalid production query index types or shape')
        if known is not None:
            return known[1]
        if any(not 0 <= v < limit for v in values):
            raise ValueError('global query index outside profile')
        mapped = values
        if self.cache is not None:
            if self.cache.closed or self.cache.tables.closed:
                raise ValueError('closed materialized cache')
            try:
                mapped = tuple(self.cache.maps[side][v] for v in values)
            except KeyError:
                raise ValueError('query row absent from immutable cache') from None
        raw = struct.pack('<32I', *mapped, *([0]*(32-count)))
        # The cache is bounded even over a long sequence of changing windows.
        if len(self.axes[side]) >= LIMIT:
            self.axes[side].clear()
        self.axes[side][values] = (values, raw)
        return raw

    def prepare(self, owner, queries, bounds, capacity):
        queries = tuple(queries); bounds = tuple(bounds)
        validate_wide(bounds, capacity, 0)
        if len(queries) != len(bounds):
            raise ValueError('query/target count differs')
        pieces = []
        header = struct.pack('<2I', 10, 16)
        for query in queries:
            if not isinstance(query, TileQuery):
                raise ValueError('TileQuery required')
            pieces.extend((header, self.axis(query.rows, 0), self.axis(query.cols, 1)))
        packed_bounds = {}
        for bound in bounds:
            if bound not in packed_bounds:
                packed_bounds[bound] = bound.to_bytes(32, 'little')
        return PreparedBatch(owner, queries, b''.join(pieces), bounds,
                             b''.join(packed_bounds[b] for b in bounds))


class PreparedDispatch:
    def __init__(self, device, tables, kernel, *, cache=None, capacity=4096):
        if (kernel not in KERNELS or type(capacity) is not int or not 0 <= capacity <= LIMIT
                or tables.closed or tables.device is not device):
            raise ValueError('invalid reusable dispatch configuration')
        if kernel != KERNELS[0] and (cache is None or cache.closed or cache.tables is not tables):
            raise ValueError('fragment dispatch requires its open materialized cache')
        if kernel != KERNELS[0]:
            from tools.fragment_scan import FragmentCache
            if not isinstance(cache, FragmentCache):
                raise ValueError('fragment-layout cache required')
        if kernel == KERNELS[0] and cache is not None:
            raise ValueError('virtual dispatch does not accept materialized inputs')
        self.device = device; self.tables = tables; self.cache = cache; self.kernel = kernel
        self.capacity = capacity; self.owned = []; self.closed = False; self.active = None
        self.token = object(); self.packer = QueryPacker(tables.profile, cache)
        self.buffers = []
        try:
            self.desc = self.guarded(LIMIT*264)
            self.targets = self.guarded(LIMIT*32)
            self.status = self.guarded(8)
            self.queue = self.guarded(capacity*44)
            self.trace = self.guarded(LIMIT*64)
            self.function = C.c_void_p()
            device.api('cuModuleGetFunction', [C.POINTER(C.c_void_p), C.c_void_p, C.c_char_p],
                       C.byref(self.function), device.module, kernel)
            profile = tables.profile
            if cache is None:
                inputs = tables.inputs(); m, n = profile.m, profile.n
            else:
                null = C.c_ulonglong(0)
                inputs = (cache.buffers[0][1], cache.buffers[1][1], null, null, null)
                m, n = len(cache.rows_a), len(cache.rows_b)
            self.audit = C.c_uint(); self.queue_capacity = C.c_uint(); self.count = C.c_uint()
            self.generation = C.c_ulonglong()
            self.arguments = (*inputs, self.desc[1], self.targets[1], tables.key_a,
                              self.status[1], self.queue[1], self.trace[1], self.audit,
                              self.queue_capacity, self.count, C.c_uint(m), C.c_uint(n),
                              C.c_uint(profile.k), C.c_uint(profile.rank), C.c_int(profile.fill), self.generation)
            self.params = (C.c_void_p*len(self.arguments))(
                *(C.cast(C.byref(v), C.c_void_p) for v in self.arguments))
        except BaseException:
            self.close(); raise

    def guarded(self, size):
        raw, pointer = self.device.guarded(size)
        self.owned.append(raw)
        value = (raw, pointer, size); self.buffers.append(value)
        return value

    def require_open(self):
        if self.closed or self.tables.closed or (self.cache is not None and self.cache.closed):
            raise ValueError('closed reusable dispatch or input cache')

    def prepare(self, queries, bounds):
        self.require_open()
        batch = self.packer.prepare(self.token, queries, bounds, self.capacity)
        if self.kernel == KERNELS[2]:
            from tools.cooperative_scan import validate_cooperative
            validate_cooperative(batch.queries)
        return batch

    def upload(self, pointer, raw):
        buffer = C.create_string_buffer(raw, len(raw))
        self.device.api('cuMemcpyHtoD_v2', [C.c_ulonglong, C.c_void_p, C.c_size_t],
                        pointer, buffer, len(raw))

    def check_buffer(self, buffer):
        raw, pointer, size = buffer
        if (self.tables.read(raw, 0, 16) != GUARD
                or self.tables.read(raw, size+16, 16) != GUARD):
            raise RuntimeError('reusable dispatch guard changed')

    def download(self, buffer, size):
        raw, pointer, maximum = buffer
        if not 0 <= size <= maximum:
            raise ValueError('download exceeds reusable buffer')
        self.check_buffer(buffer)
        return self.tables.read(pointer, 0, size) if size else b''

    def run(self, batch, generation, *, capacity=None, audit=False, current=None):
        self.require_open()
        if not isinstance(batch, PreparedBatch) or batch.owner is not self.token:
            raise ValueError('foreign prepared batch')
        capacity = self.capacity if capacity is None else capacity
        validate_wide(batch.bounds, capacity, generation)
        if capacity > self.capacity or type(audit) is not bool:
            raise ValueError('dispatch queue or audit option exceeds limits')
        def check_current():
            if current is not None and current() != generation:
                raise RuntimeError('stale dispatch generation')
        check_current()
        if batch is not self.active:
            self.active = None
            self.upload(self.desc[1], batch.descriptors)
            self.upload(self.targets[1], batch.targets)
            self.active = batch
        self.upload(self.status[1], bytes(8))
        self.audit.value = int(audit); self.queue_capacity.value = capacity
        self.count.value = len(batch.queries); self.generation.value = generation
        blocks = self.count.value//16 if self.kernel == KERNELS[2] else (self.count.value+7)//8
        self.device.api('cuLaunchKernel', [C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                        self.function, blocks, 1, 1, 256, 1, 1, 0, None, self.params, None)
        self.device.api('cuCtxSynchronize', [])
        check_current()
        result = decode_wide(self.download(self.queue, capacity*44), self.download(self.status, 8),
                             batch.bounds, capacity, generation)
        words = self.download(self.trace, len(batch.queries)*64 if audit else 0)
        self.device.last_transcripts = tuple(struct.unpack_from('<16I', words, i*64)
            for i in range(len(batch.queries))) if audit else None
        self.check_buffer(self.desc); self.check_buffer(self.targets)
        if self.cache is None: self.tables.check_guards()
        else: self.cache.check_guards()
        references = {}
        def reference(query):
            if query not in references:
                references[query] = global_reference(self.tables.profile, (query,))[0][1]
                self.device.unique_cpu_checks += 1
            return references[query]
        checked = verify_returned(result, batch.queries, reference)
        check_current()
        self.device.verified_tiles += checked
        self.device.dispatches += 1; self.device.wide_dispatches += 1
        return result

    def close(self):
        if not self.closed:
            self.device.api('cuCtxSynchronize', [])
            for pointer in reversed(self.owned):
                self.device.release(pointer)
            self.owned.clear(); self.active = None; self.closed = True
