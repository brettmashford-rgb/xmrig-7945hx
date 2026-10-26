"""Stream-ordered reset and scalar uniform-target validation; offline only. ISC."""
import ctypes as C
from dataclasses import dataclass
import struct
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.prepared_dispatch import GUARD
from tools.snapshot_scan import SnapshotDirectDispatch
from tools.resident_scan import ResidentBackend
from tools.wide_scan import validate_wide
from tools.check_tile_scan_gpu import MAX_BOUND,ScanResult
from tools.virtual_scan import global_reference
from tools.candidate_scan import verify_returned


def validate_uniform(count,bound,capacity,generation):
    if (type(count)is not int or not 1<=count<=4096 or type(bound)is not int or not 0<=bound<=MAX_BOUND
            or type(capacity)is not int or not 0<=capacity<=4096
            or type(generation)is not int or not 0<=generation<1<<64):
        raise ValueError('invalid uniform query/target/queue limits')


def uniform_count(status,count,bound,capacity,generation):
    validate_uniform(count,bound,capacity,generation)
    if type(status)is not bytes or len(status)!=8:raise ValueError('invalid uniform status size')
    total,overflow=struct.unpack('<2I',status)
    if total>count or overflow!=int(total>capacity):raise ValueError('invalid uniform count or overflow')
    return min(total,capacity)


def decode_uniform(raw,status,count,bound,capacity,generation):
    populated=uniform_count(status,count,bound,capacity,generation)
    if type(raw)is not bytes or len(raw)!=capacity*44:raise ValueError('uniform queue size differs')
    total,overflow=struct.unpack('<2I',status);records={}
    for index in range(populated):
        offset=index*44;tile,lo,hi=struct.unpack_from('<3I',raw,offset);digest=raw[offset+12:offset+44]
        if (tile>=count or tile in records or (lo|hi<<32)!=generation
                or int.from_bytes(digest,'little')>bound):
            raise ValueError('unknown, duplicate, stale or target-failing uniform candidate')
        records[tile]=digest
    return ScanResult(total,bool(overflow),records)


@dataclass(frozen=True)
class UniformPrepared:
    owner:object
    queries:Queries
    bound:int
    def __post_init__(self):
        if type(self.queries)is not Queries or type(self.queries.batch)is not FastBatch:
            raise ValueError('validated immutable uniform batch required')
        validate_uniform(len(self.queries),self.bound,0,0)


class StreamResetDispatch(SnapshotDirectDispatch):
    def validate_window(self,batch,prepared,generation,capacity,audit):
        if type(batch)is not FastBatch or batch.plan is not self.plan or prepared.owner is not self.token:
            raise ValueError('foreign resident batch or preparation')
        if (not isinstance(prepared.queries,Queries)or prepared.queries.batch is not batch
                or prepared.bounds!=(self.bound,)*(batch.stop-batch.start)):
            raise ValueError('resident query/target binding differs')
        validate_wide(prepared.bounds,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('resident queue/audit exceeds limits')

    def scan_window(self,batch,prepared,generation,*,capacity=1,audit=False,current=None):
        self.require_open()
        if self.pending or self.loaded is not None:raise ValueError('resident stream still owns a batch')
        self.validate_window(batch,prepared,generation,capacity,audit)
        self.snapshot_ready=False;self.snapshot_enqueued=False
        def check():
            if current is not None and current()!=generation:raise RuntimeError('stale resident generation')
        try:
            check();self.audit.value=int(audit);self.queue_capacity.value=capacity
            self.count.value=len(prepared.queries);self.generation.value=generation;self.first.value=batch.start
            self.loaded=(prepared,generation,capacity,audit);self.launched=False
            # Reset and both kernels share this stream. Own/drain reset work even
            # if a generation change prevents the scanner from being launched.
            self.pending=True
            self.device.api('cuMemsetD32Async',[C.c_ulonglong,C.c_uint,C.c_size_t,C.c_void_p],
                self.status[1],0,2,self.stream)
            check();self.launched=True
            self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                self.function,(self.count.value+7)//8,1,1,256,1,1,0,self.stream,self.params,None)
            self.wait();check();result,traces=self.finish()
            for axis in self.axes:self.check_buffer(axis)
            check();self.device.last_transcripts=traces
            return result
        finally:self.snapshot_ready=False

    def wait(self):
        # A stale check after reset may leave only the memset pending. Drain it
        # directly, without gathering a snapshot for a scanner that never ran.
        if self.pending and not self.launched:
            self.device.api('cuStreamSynchronize',[C.c_void_p],self.stream);self.pending=False
        else:super().wait()


class LeanDispatch(StreamResetDispatch):
    def prepare_window(self,batch):
        if type(batch)is not FastBatch or batch.plan is not self.plan:raise ValueError('foreign uniform batch')
        return UniformPrepared(self.token,Queries(batch),self.bound)

    def validate_window(self,batch,prepared,generation,capacity,audit):
        if (type(batch)is not FastBatch or batch.plan is not self.plan or type(prepared)is not UniformPrepared
                or prepared.owner is not self.token or prepared.queries.batch is not batch
                or prepared.bound!=self.bound):
            raise ValueError('foreign uniform batch, preparation or target')
        validate_uniform(len(prepared.queries),self.bound,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('uniform queue/audit exceeds limits')

    def finish(self):
        if self.loaded is None or not self.launched:raise ValueError('no launched batch')
        self.wait();batch,generation,capacity,audit=self.loaded;count=len(batch.queries)
        raw=self.tables.read(self.snapshot[0],0,self.snapshot[2]+32)
        if raw[:16]!=GUARD or raw[-16:]!=GUARD or raw[40:-16]!=GUARD*self.guard_count:
            raise RuntimeError('snapshot guard changed')
        if raw[24:40]!=struct.pack('<QII',generation,self.first.value,count):
            raise RuntimeError('stale snapshot window identity')
        self.snapshot_ready=True;status=raw[16:24]
        populated=uniform_count(status,count,batch.bound,capacity,generation)
        records=self.tables.read(self.queue[1],0,populated*44)if populated else b''
        result=decode_uniform(records,status,count,batch.bound,populated,generation)
        words=self.tables.read(self.trace[1],0,count*64)if audit else b''
        traces=tuple(struct.unpack_from('<16I',words,i*64)for i in range(count))if audit else None
        refs={}
        def reference(query):
            if query not in refs:
                refs[query]=global_reference(self.tables.profile,(query,))[0][1]
                self.device.unique_cpu_checks+=1
            return refs[query]
        self.device.verified_tiles+=verify_returned(result,batch.queries,reference)
        self.device.dispatches+=1;self.device.wide_dispatches+=1
        self.loaded=None;self.launched=False
        return result,traces


class StreamResetBackend(ResidentBackend):dispatch_type=StreamResetDispatch
class LeanBackend(ResidentBackend):dispatch_type=LeanDispatch


def new_lean_search(context,device,current,*,lean=True,start=0,on_close=None):
    if type(lean)is not bool:raise ValueError('boolean lean selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        backend=LeanBackend if lean else StreamResetBackend
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
