"""Paired-row traversal, canonical candidate IDs and two-tile B reuse; offline. ISC."""
import ctypes as C
from dataclasses import dataclass
from pool.search import NonceSearch,require_current,Hit
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.check_tile_scan_gpu import TileQuery
from tools.lean_scan import validate_uniform
from tools.transpose6_scan import Transpose6Dispatch
from tools.resident_scan import ResidentBackend


def require_pair_plan(plan):
    if type(plan)is not FastPlan or len(plan.rows)%2:
        raise ValueError('validated even row-axis count required for paired traversal')


def canonical_tile(plan,ordinal):
    require_pair_plan(plan)
    if type(ordinal)is not int or not 0<=ordinal<plan.count:raise ValueError('paired ordinal outside plan')
    pair,member=divmod(ordinal,2);row_pair,col=divmod(pair,len(plan.cols))
    return (row_pair*2+member)*len(plan.cols)+col


def traversal_ordinal(plan,tile):
    require_pair_plan(plan)
    if type(tile)is not int or not 0<=tile<plan.count:raise ValueError('canonical tile outside plan')
    row,col=divmod(tile,len(plan.cols))
    return (row//2)*(2*len(plan.cols))+2*col+(row%2)


def coverage_interval(plan,first,stop):
    """An aligned sequence of whole row pairs covers this exact canonical interval."""
    require_pair_plan(plan);period=2*len(plan.cols)
    if (any(type(v)is not int for v in(first,stop))or not 0<=first<stop<=plan.count
            or first%period or stop%period):raise ValueError('whole aligned row-pair interval required')
    return first,stop


class RowPairQueries(Queries):
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i]for i in range(*index.indices(len(self))))
        if type(index)is not int:raise TypeError('integer paired query index required')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        return TileQuery(*self.batch.plan.indices(canonical_tile(self.batch.plan,self.batch.start+index)))


@dataclass(frozen=True)
class RowPairPrepared:
    owner:object
    queries:RowPairQueries
    bound:int
    def __post_init__(self):
        if type(self.queries)is not RowPairQueries or type(self.queries.batch)is not FastBatch:
            raise ValueError('validated immutable paired batch required')
        require_pair_plan(self.queries.batch.plan);validate_uniform(len(self.queries),self.bound,0,0)


class RowPairDispatch(Transpose6Dispatch):
    kernel_entry=b'shared_b_order_control_scan'
    shared=False
    def __init__(self,device,tables,cache,plan,bound):
        require_pair_plan(plan)
        super().__init__(device,tables,cache,plan,bound)

    def prepare_window(self,batch):
        if type(batch)is not FastBatch or batch.plan is not self.plan:raise ValueError('foreign paired batch')
        return RowPairPrepared(self.token,RowPairQueries(batch),self.bound)

    def validate_window(self,batch,prepared,generation,capacity,audit):
        if (type(batch)is not FastBatch or batch.plan is not self.plan or type(prepared)is not RowPairPrepared
                or prepared.owner is not self.token or prepared.queries.batch is not batch
                or prepared.bound!=self.bound):raise ValueError('foreign paired batch, preparation or target')
        validate_uniform(len(prepared.queries),self.bound,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('paired queue/audit exceeds limits')

    def grid(self,count,first):
        return (count+(first&1)+15)//16 if self.shared else (count+7)//8

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
                self.function,self.grid(self.count.value,self.first.value),1,1,256,1,1,0,self.stream,self.params,None)
            self.wait();check();result,traces=self.finish()
            for axis in self.axes:self.check_buffer(axis)
            check();self.device.last_transcripts=traces
            return result
        finally:self.snapshot_ready=False


class SharedBDispatch(RowPairDispatch):
    kernel_entry=b'shared_b_pair_scan'
    shared=True


class RowPairBackend(ResidentBackend):dispatch_type=RowPairDispatch
class SharedBBackend(ResidentBackend):dispatch_type=SharedBDispatch


class RowPairSearch(NonceSearch):
    """Cursor is a paired traversal ordinal; every returned Hit uses canonical ID."""
    def advance(self,tiles):
        hit,cursor=super().advance(tiles)
        if hit is not None:self.hit=Hit(hit.generation,canonical_tile(self.plan,hit.tile),hit.digest)
        return self.hit,cursor


def new_shared_b_search(context,device,current,*,shared=True,start=0,on_close=None):
    if type(shared)is not bool:raise ValueError('boolean B-sharing selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job);require_pair_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        backend=SharedBBackend if shared else RowPairBackend
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return RowPairSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
