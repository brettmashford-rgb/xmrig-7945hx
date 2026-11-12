"""v084 exact B-basis A projection with bounded sparse high-byte corrections. ISC."""
import ctypes as C
import time
from pool.search import require_current
from tools import pair_depth_scan as control
from tools.job_b_tables import JobBTables
from tools.job_geometry import GeometryTables
from tools.resident_scan import ResidentBackend

MODES=('pair-direct','projected-sparse')
Batch=control.Batch
class Queries(control.Queries):
    def __init__(self,batch,mode):
        if mode not in MODES:raise ValueError('unknown projection mode')
        super().__init__(batch,'pair-direct')
def canonical(plan,mode,ordinal):
    if mode not in MODES:raise ValueError('unknown projection mode')
    return control.canonical(plan,'pair-direct',ordinal)
def inverse(plan,mode,tile):
    if mode not in MODES:raise ValueError('unknown projection mode')
    return control.inverse(plan,'pair-direct',tile)
def layout(plan,mode,ordinal):
    if mode not in MODES:raise ValueError('unknown projection mode')
    return control.layout(plan,'pair-direct',ordinal)


def guarded(owner,size):
    """Initialize both endpoints only; preparation kernels initialize every used element."""
    raw=C.c_ulonglong();device=owner.device
    device.api('cuMemAlloc_v2',[C.POINTER(C.c_ulonglong),C.c_size_t],C.byref(raw),size+32)
    device.allocations.append(raw);owner.owned.append(raw)
    data=C.create_string_buffer(b'\xa5'*16,16)
    for offset in(0,size+16):device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],C.c_ulonglong(raw.value+offset),data,16)
    return raw,C.c_ulonglong(raw.value+16),size


def check_buffer(owner,buffer):
    raw,pointer,size=buffer
    if owner.read(raw,0,16)!=b'\xa5'*16 or owner.read(raw,size+16,16)!=b'\xa5'*16:raise RuntimeError('projection buffer guard changed')


class ProjectedB(JobBTables):
    def __init__(self,device,context,current):
        self.sum_buffer=None
        p=context.profile
        if (p.k,p.rank,p.fill)!=(32768,128,64)or not 1<=p.m<=8192 or not 1<=p.n<=262144:
            raise ValueError('projection profile exceeds explicit production bounds')
        super().__init__(device,context,current)
        start=time.perf_counter();temporary=[]
        try:
            low=guarded(self,256*128);special=guarded(self,256*2);temporary=[low,special]
            self.sum_buffer=guarded(self,context.profile.n*256*2)
            device.launch(b'projection_b_coeff',(self.buffer[3],low[1],special[1]),256,128)
            warps=((context.profile.n+15)//16)*32
            device.launch(b'projection_b_sums',(self.buffer[1],low[1],special[1],self.sum_buffer[1],C.c_uint(context.profile.n)),(warps+3)//4,128)
            device.api('cuCtxSynchronize',[])
            for buffer in temporary+[self.sum_buffer]:check_buffer(self,buffer)
            for raw,pointer,size in temporary:device.release(raw);self.owned.remove(raw)
            self.check_guards();require_current(context.job,current)
            self.projection_setup_seconds=time.perf_counter()-start;self.projection_bytes=self.sum_buffer[2]
        except BaseException:self.close();raise
    def check_guards(self):
        super().check_guards()
        if self.sum_buffer is not None:check_buffer(self,self.sum_buffer)
    def stats(self):
        out=super().stats();out.update(b_projection_bytes=getattr(self,'projection_bytes',0),b_projection_setup_seconds=getattr(self,'projection_setup_seconds',0.));return out


def new_b_owner(device,context,current,mode):
    if mode not in MODES:raise ValueError('unknown projection mode')
    return (JobBTables if mode=='pair-direct'else ProjectedB)(device,context,current)


class Projection:
    def __init__(self,tables,cache):
        self.device=tables.device;self.tables=tables;self.owned=[];self.buffers=[];self.closed=False
        self.read=tables.read;start=time.perf_counter()
        try:
            m=tables.profile.m
            self.low=guarded(self,m*32768);self.row_sum=guarded(self,m*256*2)
            self.counts=guarded(self,m*256*4);self.records=guarded(self,m*256*128*2)
            self.buffers=[self.low,self.row_sum,self.counts,self.records]
            args=(cache.pointer,tables.buffers['B'][3],self.low[1],self.row_sum[1],self.counts[1],self.records[1],C.c_uint(m))
            self.device.launch(b'projection_prepare_a',args,m*256,128);self.device.api('cuCtxSynchronize',[])
            for buffer in self.buffers:check_buffer(self,buffer)
            self.setup_seconds=time.perf_counter()-start;self.bytes=sum(b[2]for b in self.buffers)
        except BaseException:self.close();raise
    def close(self):
        if self.closed:return
        self.device.api('cuCtxSynchronize',[])
        for pointer in reversed(self.owned):self.device.release(pointer)
        self.owned.clear();self.closed=True


class ProjectedDispatch(control.Dispatch):
    mode='pair-direct';kernel_entry=b'projected_pair_scan'
    def __init__(self,device,tables,cache,plan,bound):
        self.projection=None;self._projection_included=False
        owner=tables.b_cache
        if not isinstance(owner,ProjectedB)or owner.sum_buffer is None:raise ValueError('matching projected job B required')
        self.b_sum=owner.sum_buffer;self.projection=Projection(tables,cache)
        try:
            super().__init__(device,tables,cache,plan,bound)
            args=list(self.arguments);args[0]=self.projection.low[1]
            args.extend((self.projection.row_sum[1],self.projection.counts[1],self.projection.records[1],self.b_sum[1]))
            self.arguments=tuple(args);self.params=(C.c_void_p*28)(*(C.cast(C.byref(v),C.c_void_p)for v in args))
            if self.guard_count!=38:raise ValueError('projection snapshot must cover all 38 endpoints')
        except BaseException:self.close();raise
    def guarded(self,size):
        result=super().guarded(size)
        if self._allocations_seen==5 and not self._projection_included:
            self.buffers.extend(self.projection.buffers+[self.b_sum]);self._projection_included=True
        return result
    def close(self):
        if getattr(self,'closed',False):return
        super().close()
        if self.projection is not None:self.projection.close()


class ProjectedBackend(ResidentBackend):
    dispatch_type=ProjectedDispatch
    def stats(self):
        out=super().stats();p=getattr(self.dispatch,'projection',None)
        out.update(projection_bytes=getattr(p,'bytes',0),projection_setup_seconds=getattr(p,'setup_seconds',0.));return out


def new_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='pair-direct'):
    if mode not in MODES:raise ValueError('unknown projection experiment')
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident maps required')
    if mode=='projected-sparse'and not isinstance(b_owner,ProjectedB):raise ValueError('projected B owner required')
    plan=geometry.plan
    if len(plan.rows)%4 or len(plan.rows)>16 and len(plan.rows)%16:raise ValueError('unsupported paired rows')
    backend_type=control.BACKENDS['pair-direct']if mode=='pair-direct'else ProjectedBackend
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        backend=backend_type(profile,actual,plan=plan,bound=bound,current_generation=generation,on_close=on_close,tables_factory=tables_factory)
        backend.dispatch.check_current=lambda:require_current(context.job,current)
        return backend
    return control.Search(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan,mode='pair-direct')
