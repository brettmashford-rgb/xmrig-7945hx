"""One bounded row-major A cache per nonce; B stays virtual. ISC."""
import ctypes as C
import struct
import time
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan,FastCandidateBackend
from tools.production_scan import require_production

CAP=256*1024*1024
GUARD=b'\xa5'*16


def cache_size(profile):
    require_production(profile,())
    if type(profile.m)is not int:raise ValueError('integer A row count required')
    size=profile.m*32768
    if not 1<=profile.m<=8192 or size>CAP:raise ValueError('A cache exceeds 256 MiB cap')
    return size


class CachedA:
    def __init__(self,tables):
        if tables.closed:raise ValueError('closed noise tables')
        self.tables=tables;self.device=tables.device;self.closed=False;self.owned=[]
        self.bytes=cache_size(tables.profile);started=time.monotonic();raw=C.c_ulonglong()
        try:
            self.device.api('cuMemAlloc_v2',[C.POINTER(C.c_ulonglong),C.c_size_t],C.byref(raw),self.bytes+32)
            self.device.allocations.append(raw);self.owned.append(raw)
            self.raw=raw;self.pointer=C.c_ulonglong(raw.value+16)
            self.write(raw,GUARD);self.write(C.c_ulonglong(raw.value+self.bytes+16),GUARD)
            indices=self.device.allocate(struct.pack('<'+str(tables.profile.m)+'I',*range(tables.profile.m)))
            self.owned.append(indices);p=tables.profile
            args=(*tables.inputs(),indices,self.pointer,C.c_uint(p.m),C.c_uint(0),C.c_uint(p.m),
                  C.c_uint(p.n),C.c_uint(p.k),C.c_uint(p.rank),C.c_int(p.fill))
            words=self.bytes//4
            self.device.launch(b'materialize_selected_rows',args,(words+127)//128,128)
            self.device.api('cuCtxSynchronize',[]);self.check_guards()
            self.setup_seconds=time.monotonic()-started
        except BaseException:self.close();raise

    def write(self,pointer,raw):
        buffer=C.create_string_buffer(raw,len(raw))
        self.device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],pointer,buffer,len(raw))

    def check_guards(self):
        if self.closed:raise ValueError('closed A cache')
        if (self.tables.read(self.raw,0,16)!=GUARD or self.tables.read(self.raw,self.bytes+16,16)!=GUARD):
            raise RuntimeError('A materialization guard changed')

    def close(self):
        if not self.closed:
            self.closed=True;self.device.api('cuCtxSynchronize',[])
            for pointer in reversed(self.owned):self.device.release(pointer)
            self.owned.clear()


class Source:
    def __init__(self,cache):self.cache=cache;self.noise=cache.tables
    @property
    def closed(self):return self.cache.closed or self.noise.closed
    def __getattr__(self,name):return getattr(self.noise,name)
    def check_guards(self):self.noise.check_guards();self.cache.check_guards()


def attach(dispatch,cache):
    if (dispatch.closed or cache.closed or dispatch.tables is not cache.tables
            or dispatch.cache is not None or dispatch.kernel!=b'production_virtual_tile_scan'):
        raise ValueError('cached-A attachment requires its own open virtual dispatch')
    function=C.c_void_p()
    dispatch.device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                        C.byref(function),dispatch.device.module,b'cached_a_virtual_b_scan')
    arguments=(C.c_ulonglong(cache.pointer.value),)+dispatch.arguments[1:]
    params=(C.c_void_p*len(arguments))(*(C.cast(C.byref(v),C.c_void_p)for v in arguments))
    # Retain ctypes values and never mutate the original noise-table pointers.
    dispatch.arguments=arguments;dispatch.params=params;dispatch.function=function
    dispatch.tables=Source(cache)


class CachedABackend(FastCandidateBackend):
    def __init__(self,*args,**kwargs):
        self.a_cache=None
        super().__init__(*args,**kwargs)
        try:
            self.a_cache=CachedA(self.tables);attach(self.dispatch,self.a_cache)
        except BaseException:self.close();raise
    def stats(self):
        value=super().stats();value['a_cache_bytes']=self.a_cache.bytes if self.a_cache is not None else 0
        value['a_cache_seconds']=self.a_cache.setup_seconds if self.a_cache is not None and hasattr(self.a_cache,'setup_seconds')else 0.
        return value
    def close(self):
        try:
            if self.a_cache is not None:self.a_cache.close()
        finally:super().close()


def new_cached_a_search(context,device,current,*,start=0,on_close=None):
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return CachedABackend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
