"""v083 native direct/graph dispatch of unchanged pair-direct; one 16K window. ISC."""
import ctypes as C
from functools import lru_cache
import os,time
from pathlib import Path
from pool.search import require_current
from tools import pair_depth_scan as control
from tools.job_geometry import GeometryTables
from tools.resident_scan import ResidentBackend

MODES=('pair-direct','native-direct','native-graph')
Batch=control.Batch
class Queries(control.Queries):
    def __init__(self,batch,mode):
        if mode not in MODES:raise ValueError('unknown dispatch mode')
        super().__init__(batch,'pair-direct')
def canonical(plan,mode,ordinal):
    if mode not in MODES:raise ValueError('unknown dispatch mode')
    return control.canonical(plan,'pair-direct',ordinal)
def inverse(plan,mode,tile):
    if mode not in MODES:raise ValueError('unknown dispatch mode')
    return control.inverse(plan,'pair-direct',tile)
def layout(plan,mode,ordinal):
    if mode not in MODES:raise ValueError('unknown dispatch mode')
    return control.layout(plan,'pair-direct',ordinal)


class KernelParams(C.Structure):
    _fields_=[('func',C.c_void_p),('gx',C.c_uint),('gy',C.c_uint),('gz',C.c_uint),
        ('bx',C.c_uint),('by',C.c_uint),('bz',C.c_uint),('shared',C.c_uint),
        ('params',C.POINTER(C.c_void_p)),('extra',C.POINTER(C.c_void_p))]
class MemsetParams(C.Structure):
    _fields_=[('dst',C.c_ulonglong),('pitch',C.c_size_t),('value',C.c_uint),('element_size',C.c_uint),('width',C.c_size_t),('height',C.c_size_t)]
class Api(C.Structure):
    _fields_=[(n,C.c_void_p)for n in('reset','launch','sync','copy','set_node','graph_launch')]
class Call(C.Structure):
    _fields_=[('status',C.c_ulonglong),('snapshot',C.c_ulonglong),('host',C.c_void_p),('bytes',C.c_size_t),('stream',C.c_void_p),
        ('scanner',KernelParams),('collector',KernelParams),('executable',C.c_void_p),('scan_node',C.c_void_p),('collector_node',C.c_void_p),
        ('phase',C.c_uint),('calls',C.c_ulonglong*6)]


@lru_cache(maxsize=2)
def native_library(path):
    lib=C.CDLL(str(Path(path).resolve()))
    lib.ph_abi_size.argtypes=[C.c_uint];lib.ph_abi_size.restype=C.c_size_t
    for index,kind in enumerate((Api,Call,KernelParams,MemsetParams)):
        if lib.ph_abi_size(index)!=C.sizeof(kind):raise ValueError('native dispatch ABI size differs')
    lib.ph_dispatch.argtypes=[C.c_uint,C.POINTER(Api),C.POINTER(Call)];lib.ph_dispatch.restype=C.c_int
    return lib


class SnapshotSource:
    """Feed exactly the completed C readback into the unchanged guard/CPU decoder."""
    def __init__(self,source,dispatch):self.source=source;self.dispatch=dispatch
    def __getattr__(self,name):return getattr(self.source,name)
    def read(self,pointer,offset,size):
        d=self.dispatch
        if d.prefetched is not None and pointer.value==d.snapshot[0].value and offset==0 and size==d.snapshot[2]+32:
            raw=d.prefetched;d.prefetched=None;return raw
        return self.source.read(pointer,offset,size)


class NativeDispatch(control.Dispatch):
    mode='pair-direct';kernel_entry=b'a_pair_direct_scan';execution='native-direct'
    def __init__(self,*args,**kwargs):
        self.graph=C.c_void_p();self.executable=C.c_void_p();self.prefetched=None;self.native_windows=0
        super().__init__(*args,**kwargs)
        start=time.perf_counter()
        try:
            path=os.environ.get('PEARL_DISPATCH_LIBRARY')
            if not path:raise ValueError('verified native dispatch library required')
            self.native=native_library(path)
            names=('cuMemsetD32Async','cuLaunchKernel','cuStreamSynchronize','cuMemcpyDtoH_v2',
                'cuGraphExecKernelNodeSetParams','cuGraphLaunch')
            self.native_api=Api(*(C.cast(getattr(self.device.lib,n),C.c_void_p).value if i<4 or self.execution=='native-graph'else None for i,n in enumerate(names)))
            self.host_snapshot=C.create_string_buffer(self.snapshot[2]+32)
            self.call=Call();self.call.status=self.status[1].value;self.call.snapshot=self.snapshot[0].value
            self.call.host=C.cast(self.host_snapshot,C.c_void_p).value;self.call.bytes=C.sizeof(self.host_snapshot);self.call.stream=self.stream.value
            self.call.scanner=KernelParams(self.function,1,1,1,256,1,1,0,self.params,None)
            self.call.collector=KernelParams(self.collector,(self.snapshot[2]+127)//128,1,1,128,1,1,0,self.snapshot_params,None)
            if self.call.bytes!=504:raise ValueError('native bridge requires the complete 28-guard snapshot')
            if self.execution=='native-graph':self.build_graph()
            self.tables=SnapshotSource(self.tables,self)
            self.native_setup_seconds=time.perf_counter()-start
        except BaseException:self.close();raise

    def build_graph(self):
        device=self.device
        device.api('cuGraphCreate',[C.POINTER(C.c_void_p),C.c_uint],C.byref(self.graph),0)
        reset=C.c_void_p();scan=C.c_void_p();collector=C.c_void_p()
        memset=MemsetParams(self.status[1].value,0,0,4,2,1)
        device.api('cuGraphAddMemsetNode',[C.POINTER(C.c_void_p),C.c_void_p,C.POINTER(C.c_void_p),C.c_size_t,C.POINTER(MemsetParams),C.c_void_p],
            C.byref(reset),self.graph,None,0,C.byref(memset),device.context)
        for out,dependency,parameters in((scan,reset,self.call.scanner),(collector,scan,self.call.collector)):
            deps=(C.c_void_p*1)(dependency)
            device.api('cuGraphAddKernelNode',[C.POINTER(C.c_void_p),C.c_void_p,C.POINTER(C.c_void_p),C.c_size_t,C.POINTER(KernelParams)],
                C.byref(out),self.graph,deps,1,C.byref(parameters))
        device.api('cuGraphInstantiateWithFlags',[C.POINTER(C.c_void_p),C.c_void_p,C.c_ulonglong],C.byref(self.executable),self.graph,0)
        self.call.executable=self.executable.value;self.call.scan_node=scan.value;self.call.collector_node=collector.value

    def scan_window(self,batch,prepared,generation,*,capacity=1,audit=False,current=None):
        self.require_open()
        if self.pending or self.loaded is not None:raise ValueError('native stream still owns unfinished work')
        self.validate_window(batch,prepared,generation,capacity,audit)
        def check():
            if current is not None and current()!=generation:raise RuntimeError('stale native generation')
        try:
            check();self.prefetched=None;self.snapshot_ready=False
            self.audit.value=int(audit);self.queue_capacity.value=capacity;self.count.value=len(prepared.queries)
            self.generation.value=generation;self.first.value=batch.start
            self.call.scanner.gx=self.grid(self.count.value,self.first.value)
            self.loaded=(prepared,generation,capacity,audit);self.launched=True;self.snapshot_enqueued=True
            self.pending=True
            result=self.native.ph_dispatch(int(self.execution=='native-graph'),C.byref(self.native_api),C.byref(self.call))
            if result:raise RuntimeError('native '+self.execution+' phase '+str(self.call.phase)+': CUDA error '+str(result))
            self.pending=False;self.native_windows+=1
            self.prefetched=self.host_snapshot.raw
            check();result,traces=self.finish()
            for axis in self.axes:self.check_buffer(axis)
            check();self.device.last_transcripts=traces;return result
        finally:self.prefetched=None;self.snapshot_ready=False

    def close(self):
        if getattr(self,'closed',False):return
        self.wait()
        if self.executable.value:
            self.device.api('cuGraphExecDestroy',[C.c_void_p],self.executable);self.executable=C.c_void_p()
        if self.graph.value:
            self.device.api('cuGraphDestroy',[C.c_void_p],self.graph);self.graph=C.c_void_p()
        super().close()


class GraphDispatch(NativeDispatch):execution='native-graph'
class NativeBackend(ResidentBackend):dispatch_type=NativeDispatch
class GraphBackend(ResidentBackend):dispatch_type=GraphDispatch
BACKENDS={'pair-direct':control.BACKENDS['pair-direct'],'native-direct':NativeBackend,'native-graph':GraphBackend}


def new_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='pair-direct'):
    if mode not in MODES:raise ValueError('unknown dispatch experiment')
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident maps required')
    plan=geometry.plan
    if len(plan.rows)%4 or len(plan.rows)>16 and len(plan.rows)%16:raise ValueError('unsupported paired rows')
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        backend=BACKENDS[mode](profile,actual,plan=plan,bound=bound,current_generation=generation,on_close=on_close,tables_factory=tables_factory)
        backend.dispatch.check_current=lambda:require_current(context.job,current)
        return backend
    return control.Search(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan,mode='pair-direct')
