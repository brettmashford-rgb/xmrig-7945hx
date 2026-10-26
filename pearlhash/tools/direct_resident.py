"""Direct resident canonical maps; one scanner launch per window. ISC."""
import ctypes as C
from pool.search import NonceSearch,require_current
from tools.resident_scan import ResidentDispatch,ResidentBackend
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.wide_scan import validate_wide


class DirectDispatch(ResidentDispatch):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        try:
            self.device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                C.byref(self.function),self.device.module,b'resident_direct_cached_a_scan')
            self.arguments=(*self.arguments[:5],self.axes[0][1],*self.arguments[6:],self.axes[1][1],
                C.c_uint(len(self.plan.rows)),C.c_uint(len(self.plan.cols)),self.first)
            self.params=(C.c_void_p*len(self.arguments))(
                *(C.cast(C.byref(value),C.c_void_p)for value in self.arguments))
        except BaseException:self.close();raise

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
        self.generation.value=generation;self.first.value=batch.start
        self.loaded=(prepared,generation,capacity,audit);self.launched=False
        # Explicitly finish the pageable status upload before nonblocking stream work.
        self.device.api('cuCtxSynchronize',[]);check()
        # Direct axes are read by this single scanner launch; no descriptor builder.
        self.pending=True;self.launched=True
        self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
            self.function,(self.count.value+7)//8,1,1,256,1,1,0,self.stream,self.params,None)
        self.wait();check()
        result,traces=self.finish()
        for axis in self.axes:self.check_buffer(axis)
        check();self.device.last_transcripts=traces
        return result


class DirectBackend(ResidentBackend):
    dispatch_type=DirectDispatch


def new_direct_search(context,device,current,*,start=0,on_close=None):
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return DirectBackend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
