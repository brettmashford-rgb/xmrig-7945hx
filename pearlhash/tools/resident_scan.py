"""One-stream resident canonical axes and targets; GPU-built descriptors. ISC."""
import ctypes as C
import time
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.cached_a import CachedA,attach
from tools.prepared_dispatch import PreparedBatch,KERNELS
from tools.stream_scan import StreamDispatch
from tools.production_scan import ProductionCandidateScanner
from tools.virtual_scan import VirtualTables
from tools.wide_scan import validate_wide


class ResidentDispatch(StreamDispatch):
    def __init__(self,device,tables,cache,plan,bound):
        self.plan=plan;self.bound=bound;self.builder=C.c_void_p()
        super().__init__(device,tables,KERNELS[0])
        try:
            attach(self,cache)
            self.axes=[]
            for entries in (plan.rows,plan.cols):
                raw=b''.join(axis.packed for axis in entries);buffer=self.guarded(len(raw))
                self.upload(buffer[1],raw);self.axes.append(buffer)
            self.upload(self.targets[1],bound.to_bytes(32,'little')*4096)
            device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                       C.byref(self.builder),device.module,b'resident_query_descriptors')
            self.first=C.c_uint();self.builder_count=C.c_uint()
            self.builder_args=(self.axes[0][1],self.axes[1][1],C.c_uint(len(plan.rows)),C.c_uint(len(plan.cols)),
                               self.first,self.builder_count,self.desc[1])
            self.builder_params=(C.c_void_p*len(self.builder_args))(
                *(C.cast(C.byref(value),C.c_void_p)for value in self.builder_args))
            device.api('cuCtxSynchronize',[])
        except BaseException:self.close();raise

    def prepare_window(self,batch):
        if type(batch)is not FastBatch or batch.plan is not self.plan:raise ValueError('foreign resident batch')
        count=batch.stop-batch.start
        return PreparedBatch(self.token,Queries(batch),b'',(self.bound,)*count,b'')

    def scan_window(self,batch,prepared,generation,*,capacity=1,audit=False,current=None):
        self.require_open()
        if self.pending or self.loaded is not None:raise ValueError('resident stream still owns a batch')
        if type(batch)is not FastBatch or batch.plan is not self.plan or prepared.owner is not self.token:
            raise ValueError('foreign resident batch or preparation')
        if (not isinstance(prepared.queries,Queries)or prepared.queries.batch is not batch
                or prepared.bounds!=(self.bound,)*(batch.stop-batch.start)):
            raise ValueError('resident query/target binding differs')
        validate_wide(prepared.bounds,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('resident queue/audit exceeds limits')
        def check():
            if current is not None and current()!=generation:raise RuntimeError('stale resident generation')
        check();self.upload(self.status[1],bytes(8))
        self.audit.value=int(audit);self.queue_capacity.value=capacity;self.count.value=len(prepared.queries)
        self.generation.value=generation;self.first.value=batch.start;self.builder_count.value=self.count.value
        self.loaded=(prepared,generation,capacity,audit);self.launched=False
        # Explicitly finish the pageable status upload before nonblocking stream work.
        self.device.api('cuCtxSynchronize',[]);check()
        # Builder then scanner use the SAME stream, guaranteeing descriptor visibility.
        self.pending=True;self.launched=True
        self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
            self.builder,(self.count.value*66+127)//128,1,1,128,1,1,0,self.stream,self.builder_params,None)
        check()
        # Same-stream ordering handles the dependency without a host wait.
        self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
            self.function,(self.count.value+7)//8,1,1,256,1,1,0,self.stream,self.params,None)
        self.wait();check()
        result,traces=self.finish()
        for axis in self.axes:self.check_buffer(axis)
        check();self.device.last_transcripts=traces
        return result


class ResidentBackend:
    def __init__(self,profile,device,*,plan,bound,current_generation=None,on_close=None):
        if (not isinstance(device,ProductionCandidateScanner)or type(plan)is not FastPlan
                or plan.profile!=(profile.m,profile.n,profile.k,profile.rank,profile.fill)):
            raise ValueError('production scanner and matching immutable plan required')
        validate_wide([bound],1,0)
        self.device=device;self.plan=plan;self.bound=bound;self.current_generation=current_generation;self.on_close=on_close
        self.closed=False;self.tables=self.cache=self.dispatch=None;self.batch=self.prepared=None;self.generation=None
        self.preparations=0;self.dispatches=0;self.prepare_seconds=0.;self.scan_seconds=0.;self.buffer_allocations=0;self.buffer_bytes=0
        try:
            self.tables=VirtualTables(device,profile);self.cache=CachedA(self.tables)
            self.dispatch=ResidentDispatch(device,self.tables,self.cache,plan,bound)
            self.buffer_allocations=len(self.dispatch.owned);self.buffer_bytes=sum(buf[2]+32 for buf in self.dispatch.buffers)
        except BaseException:self.close();raise

    def __call__(self,batch,capacity,generation):
        if self.closed:raise ValueError('closed resident backend')
        if self.generation is not None and self.generation!=generation:raise ValueError('nonce generation changed')
        if self.current_generation is not None and self.current_generation()!=generation:raise ValueError('stale generation')
        self.generation=generation
        if batch is not self.batch:
            started=time.monotonic();self.prepared=self.dispatch.prepare_window(batch);self.batch=batch
            self.prepare_seconds+=time.monotonic()-started;self.preparations+=1
        started=time.monotonic()
        try:result=self.dispatch.scan_window(batch,self.prepared,generation,capacity=capacity,current=self.current_generation)
        finally:self.scan_seconds+=time.monotonic()-started
        self.dispatches+=1;return result

    def stats(self):
        return dict(prepared_batches=self.preparations,dispatches=self.dispatches,prepare_seconds=self.prepare_seconds,
            scan_seconds=self.scan_seconds,dispatch_buffer_allocations=self.buffer_allocations,dispatch_buffer_bytes=self.buffer_bytes,
            a_cache_bytes=getattr(self.cache,'bytes',0),a_cache_seconds=getattr(self.cache,'setup_seconds',0.),closed=self.closed)

    def close(self):
        if self.closed:return
        self.closed=True;error=None
        for resource in (self.dispatch,self.cache,self.tables):
            if resource is not None:
                try:resource.close()
                except BaseException as exc:error=error or exc
        self.batch=self.prepared=None
        if self.on_close is not None:self.on_close(self.stats())
        if error is not None:raise error


def new_resident_search(context,device,current,*,start=0,on_close=None):
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return ResidentBackend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
