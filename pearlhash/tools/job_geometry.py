"""Exclusive job-owned immutable plan/maps; fresh nonce buffers and v060 math. ISC."""
import ctypes as C
import time
from pool.search import require_current
from tools.fast_plan import FastPlan
from tools.shared_b_scan import SharedBBackend,RowPairSearch,require_pair_plan
from tools.virtual_scan import VirtualTables
from tools.prepared_dispatch import GUARD


def geometry_binding(job):
    p=job.profile
    return (job.job_key,job.cert_version,p.m,p.n,p.k,p.rank,p.rows.encoded,p.cols.encoded)


class JobGeometry:
    def __init__(self,device,job,current,*,maps=False):
        require_current(job,current)
        if type(maps)is not bool:raise ValueError('boolean resident-map selector required')
        self.device=device;self.binding=geometry_binding(job);self.maps=maps
        self.closed=False;self.leased=False;self.leases=0;self.owned=[];self.axes=[];self.upload_bytes=0
        started=time.perf_counter()
        try:
            self.plan=FastPlan.from_job(job);require_pair_plan(self.plan)
            if maps:
                for entries in (self.plan.rows,self.plan.cols):
                    raw=b''.join(axis.packed for axis in entries);allocation=C.c_ulonglong()
                    device.api('cuMemAlloc_v2',[C.POINTER(C.c_ulonglong),C.c_size_t],C.byref(allocation),len(raw)+32)
                    # Record ownership before any upload can fail.
                    device.allocations.append(allocation);self.owned.append(allocation)
                    pointer=C.c_ulonglong(allocation.value+16);self.axes.append((allocation,pointer,len(raw)))
                    initial=C.create_string_buffer(b'\xa5'*(len(raw)+32),len(raw)+32)
                    device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],allocation,initial,len(raw)+32)
                    data=C.create_string_buffer(raw,len(raw))
                    device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],pointer,data,len(raw))
                    self.upload_bytes+=len(raw)
                device.api('cuCtxSynchronize',[]);self.check_guards()
            require_current(job,current);self.setup_seconds=time.perf_counter()-started
        except BaseException:self.close();raise

    read=VirtualTables.read

    def validate(self,context,device,current):
        require_current(context.job,current)
        p=context.profile
        if (self.closed or device is not self.device or geometry_binding(context.job)!=self.binding
                or (p.m,p.n,p.k,p.rank,p.fill)!=self.plan.profile):
            raise ValueError('foreign or closed job geometry')

    def check_guards(self):
        if self.closed:raise ValueError('closed job geometry')
        for raw,pointer,size in self.axes:
            if self.read(raw,0,16)!=GUARD or self.read(raw,size+16,16)!=GUARD:
                raise RuntimeError('job geometry guard changed')

    def acquire(self,context,device,current):
        self.validate(context,device,current)
        if self.leased:raise ValueError('job geometry already leased')
        self.check_guards();self.leased=True;self.leases+=1

    def borrow_axes(self,device,plan):
        if self.closed or not self.maps or not self.leased or device is not self.device or plan is not self.plan:
            raise ValueError('foreign, unleased or closed geometry axes')
        return list(self.axes)

    def release(self):
        if not self.leased:raise ValueError('job geometry lease already released')
        self.leased=False

    def close(self):
        if self.closed:return
        if self.leased:raise ValueError('cannot free leased job geometry')
        self.closed=True
        for pointer in reversed(self.owned):self.device.release(pointer)
        self.owned.clear()

    def stats(self):
        return dict(plan_builds=1,map_upload_bytes=self.upload_bytes,geometry_leases=self.leases,
            setup_seconds=getattr(self,'setup_seconds',0.),resident_maps=self.maps,closed=self.closed)


class GeometryTables(VirtualTables):
    def __init__(self,device,profile,*,context,current,b_owner,geometry):
        self.geometry_lease=None
        geometry.acquire(context,device,current);self.geometry_lease=geometry
        self.resident_geometry=geometry if geometry.maps else None
        try:super().__init__(device,profile,b_cache=b_owner)
        except BaseException:
            if self.geometry_lease is not None:self.geometry_lease.release();self.geometry_lease=None
            raise

    def close(self):
        try:super().close()
        finally:
            if self.closed and self.geometry_lease is not None:
                self.geometry_lease.release();self.geometry_lease=None


def new_geometry_search(context,device,current,b_owner,geometry,*,start=0,on_close=None):
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    plan=geometry.plan
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):
            b_owner.validate_context(context,current)
            return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        return SharedBBackend(profile,actual,plan=plan,bound=bound,current_generation=generation,
            on_close=on_close,tables_factory=tables_factory)
    return RowPairSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
