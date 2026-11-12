"""v076 256-thread CTA8 consumer scheduling with 16K dispatches. ISC."""
import ctypes as C
from dataclasses import dataclass
import struct
import time
from pool.search import NonceSearch,Hit,require_current
from tools.cta_b_scan import CtaBDispatch
from tools.fast_plan import FastPlan
from tools.check_tile_scan_gpu import TileQuery,MAX_BOUND,ScanResult
from tools.resident_scan import ResidentBackend
from tools.job_geometry import GeometryTables
from tools.virtual_scan import global_reference
from tools.candidate_scan import verify_returned
from tools.prepared_dispatch import GUARD

MODES=('wide16k','wide16k-schedule4','wide16k-schedule8')
ENTRIES={'wide16k':b'cta_b8_scan','wide16k-schedule4':b'wide_schedule4_scan','wide16k-schedule8':b'wide_schedule8_scan'}
THREADS={m:256 for m in MODES}


def layout(plan,mode,ordinal):
    if mode not in MODES or type(ordinal)is not int or not 0<=ordinal<plan.count:raise ValueError('experimental ordinal outside plan')
    rows,columns=len(plan.rows),len(plan.cols)
    if mode.startswith('panel'):
        full=columns//16;full_tiles=rows*16
        if ordinal<full*full_tiles:first=ordinal//full_tiles*16;width=16;local=ordinal%full_tiles
        else:first=full*16;width=columns-first;local=ordinal-full*full_tiles
    else:first=0;width=columns;local=ordinal
    group=min(rows,16 if mode.startswith('small')else 32)
    row=group*((local//group)//width)+local%group;col=first+(local//group)%width
    return row*columns+col,first,width,local


def canonical(plan,mode,ordinal):return layout(plan,mode,ordinal)[0]


def inverse(plan,mode,tile):
    if type(tile)is not int or not 0<=tile<plan.count:raise ValueError('canonical tile outside plan')
    rows,columns=len(plan.rows),len(plan.cols);row,col=divmod(tile,columns)
    group=min(rows,16 if mode.startswith('small')else 32)
    if mode.startswith('panel'):
        first=col//16*16;width=min(16,columns-first)
        return (first//16)*(rows*16)+(row//group)*(group*width)+(col-first)*group+row%group
    return (row//group)*(group*columns)+col*group+row%group


def validate(count,bound,capacity,generation):
    if (type(count)is not int or not 1<=count<=16384 or type(bound)is not int or not 0<=bound<=MAX_BOUND
            or type(capacity)is not int or not 0<=capacity<=16384 or type(generation)is not int or not 0<=generation<1<<64):
        raise ValueError('invalid experimental query/target/queue limits')


def status_count(raw,count,bound,capacity,generation):
    validate(count,bound,capacity,generation)
    if type(raw)is not bytes or len(raw)!=8:raise ValueError('invalid experimental status')
    total,overflow=struct.unpack('<2I',raw)
    if total>count or overflow!=int(total>capacity):raise ValueError('invalid experimental overflow/count')
    return min(total,capacity)


def decode(raw,status,count,bound,capacity,generation):
    populated=status_count(status,count,bound,capacity,generation)
    if type(raw)is not bytes or len(raw)!=capacity*44:raise ValueError('experimental queue size differs')
    total,overflow=struct.unpack('<2I',status);records={}
    for index in range(populated):
        tile,lo,hi=struct.unpack_from('<3I',raw,index*44);digest=raw[index*44+12:index*44+44]
        if (tile>=count or tile in records or (lo|(hi<<32))!=generation or int.from_bytes(digest,'little')>bound):
            raise ValueError('unknown, duplicate, stale or target-failing candidate')
        records[tile]=digest
    return ScanResult(total,bool(overflow),records)


@dataclass(frozen=True)
class Batch:
    plan:FastPlan
    start:int
    stop:int
    def __post_init__(self):
        if (type(self.plan)is not FastPlan or any(type(v)is not int for v in(self.start,self.stop))
                or not 0<=self.start<self.stop<=self.plan.count or self.stop-self.start>16384):raise ValueError('invalid experimental batch')


class Queries:
    def __init__(self,batch,mode):self.batch=batch;self.mode=mode
    def __len__(self):return self.batch.stop-self.batch.start
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i]for i in range(*index.indices(len(self))))
        if type(index)is not int:raise TypeError('integer query index required')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        return TileQuery(*self.batch.plan.indices(canonical(self.batch.plan,self.mode,self.batch.start+index)))


@dataclass(frozen=True)
class Prepared:
    owner:object
    queries:Queries
    bound:int


class Dispatch(CtaBDispatch):
    mode='wide16k';kernel_entry=b'cta_b8_scan'
    def guarded(self,size):
        self._allocations_seen+=1;initial=self._allocations_seen<=5
        if self.mode in MODES and initial:
            size={4096*264:16384*264,4096*32:16384*32,4096*44:16384*44,4096*64:16384*64}.get(size,size)
        result=super().guarded(size)
        # Insert the panel before SnapshotMixin captures its complete guard list.
        if self._allocations_seen==5 and self.mode.startswith('panel'):
            self.panel_buffer=super().guarded(112+min(16,len(self._plan.cols))*524288)
        return result

    def __init__(self,device,tables,cache,plan,bound):
        self._allocations_seen=0;self._plan=plan;self.limit=16384
        self.window_preparation=None;self.block_threads=THREADS[self.mode];self.panel_ready=None;self.panel_builds=0;self.panel_seconds=0.
        super().__init__(device,tables,cache,plan,bound)
        try:
            self.capacity=self.limit
            if self.mode in MODES:self.upload(self.targets[1],bound.to_bytes(32,'little')*self.limit)
            self.original_ub=self.arguments[1];self.original_pb=self.arguments[3]
            if self.mode.startswith('panel'):
                self.panel_columns=C.c_ulonglong();self.panel_width=C.c_uint();self.local_first=C.c_uint()
                args=list(self.arguments);args[20]=self.panel_columns;args[22]=self.panel_width;args[23]=self.local_first
                if self.mode=='panel':args[1]=self.panel_buffer[1]
                self.arguments=tuple(args);self.params=(C.c_void_p*24)(*(C.cast(C.byref(v),C.c_void_p)for v in self.arguments))
                self.materializer=C.c_void_p()
                device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],C.byref(self.materializer),device.module,b'build_b_panel')
        except BaseException:self.close();raise

    def group(self):return min(len(self.plan.rows),16 if self.mode.startswith('small')else 32)
    def grid(self,count,first):
        group=self.group();return (count+first%group+group-1)//group

    def prepare_window(self,batch):
        if type(batch)is not Batch or batch.plan is not self.plan:raise ValueError('foreign experimental batch')
        if batch.stop-batch.start>self.limit:raise ValueError('experimental batch exceeds limit')
        if self.pending or self.loaded is not None:raise ValueError('stream owns an unfinished preparation')
        self.window_preparation=None
        if self.mode.startswith('panel'):
            _,first,width,local=layout(self.plan,self.mode,batch.start)
            if batch.stop-batch.start>len(self.plan.rows)*width-local:raise ValueError('batch crosses B panel boundary')
            self.panel_columns.value=self.axes[1][1].value+first*128;self.panel_width.value=width;self.local_first.value=local
            if self.mode=='panel'and self.panel_ready!=first:self.build_panel(first,width)
        self.window_preparation=Prepared(self.token,Queries(batch,self.mode),self.bound)
        return self.window_preparation

    def build_panel(self,first,width):
        started=time.perf_counter();self.check_current();self.pending=True;self.launched=False
        args=(self.original_ub,self.original_pb,self.panel_columns,self.panel_buffer[1],self.panel_width,C.c_uint(self.tables.profile.n))
        params=(C.c_void_p*len(args))(*(C.cast(C.byref(v),C.c_void_p)for v in args))
        try:
            self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                self.materializer,width,1,1,256,1,1,0,self.stream,params,None)
            self.wait();self.check_current()
            flags=self.tables.read(self.panel_buffer[1],0,width*4)
            self.panel_ready=first if struct.unpack('<'+'I'*width,flags)==(1,)*width else None
            self.panel_builds+=1
        finally:
            if self.pending:self.wait()
            self.panel_seconds+=time.perf_counter()-started

    def validate_window(self,batch,prepared,generation,capacity,audit):
        if (type(batch)is not Batch or batch.plan is not self.plan or type(prepared)is not Prepared
                or prepared is not self.window_preparation or prepared.owner is not self.token or prepared.queries.batch is not batch or prepared.queries.mode!=self.mode
                or prepared.bound!=self.bound):raise ValueError('foreign experimental batch/preparation/target')
        validate(len(prepared.queries),self.bound,capacity,generation)
        if len(prepared.queries)>self.limit or capacity>self.capacity or type(audit)is not bool:raise ValueError('experimental capacity/audit differs')

    def scan_window(self,batch,prepared,generation,*,capacity=1,audit=False,current=None):
        self.require_open()
        if self.pending or self.loaded is not None:raise ValueError('experimental stream still owns work')
        self.validate_window(batch,prepared,generation,capacity,audit);self.snapshot_ready=False;self.snapshot_enqueued=False
        def check():
            if current is not None and current()!=generation:raise RuntimeError('stale experimental generation')
        try:
            check();self.audit.value=int(audit);self.queue_capacity.value=capacity;self.count.value=len(prepared.queries)
            self.generation.value=generation;self.first.value=batch.start
            self.loaded=(prepared,generation,capacity,audit);self.launched=False;self.pending=True
            self.device.api('cuMemsetD32Async',[C.c_ulonglong,C.c_uint,C.c_size_t,C.c_void_p],self.status[1],0,2,self.stream)
            check();self.launched=True
            self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                self.function,self.grid(self.count.value,self.first.value),1,1,self.block_threads,1,1,0,self.stream,self.params,None)
            self.wait();check();result,traces=self.finish()
            for axis in self.axes:self.check_buffer(axis)
            check();self.device.last_transcripts=traces;return result
        finally:self.snapshot_ready=False

    def finish(self):
        if self.loaded is None or not self.launched:raise ValueError('no launched experimental batch')
        self.wait();prepared,generation,capacity,audit=self.loaded;count=len(prepared.queries)
        raw=self.tables.read(self.snapshot[0],0,self.snapshot[2]+32)
        if raw[:16]!=GUARD or raw[-16:]!=GUARD or raw[40:-16]!=GUARD*self.guard_count:raise RuntimeError('experimental snapshot guard changed')
        if raw[24:40]!=struct.pack('<QII',generation,self.first.value,count):raise RuntimeError('stale experimental snapshot identity')
        self.snapshot_ready=True;status=raw[16:24];populated=status_count(status,count,prepared.bound,capacity,generation)
        records=self.tables.read(self.queue[1],0,populated*44)if populated else b''
        result=decode(records,status,count,prepared.bound,populated,generation)
        words=self.tables.read(self.trace[1],0,count*64)if audit else b''
        traces=tuple(struct.unpack_from('<16I',words,i*64)for i in range(count))if audit else None
        refs={}
        def reference(query):
            if query not in refs:refs[query]=global_reference(self.tables.profile,(query,))[0][1];self.device.unique_cpu_checks+=1
            return refs[query]
        self.device.verified_tiles+=verify_returned(result,prepared.queries,reference)
        self.device.dispatches+=1;self.device.wide_dispatches+=1;self.loaded=None;self.launched=False
        return result,traces


DISPATCHES={m:type('Dispatch_'+m.replace('-','_'),(Dispatch,),{'mode':m,'kernel_entry':ENTRIES[m]})for m in MODES}
BACKENDS={m:type('Backend_'+m.replace('-','_'),(ResidentBackend,),{'dispatch_type':DISPATCHES[m]})for m in MODES}


class Search(NonceSearch):
    def __init__(self,*args,mode,**kwargs):self.mode=mode;super().__init__(*args,**kwargs)
    def advance(self,tiles):
        if self.closed or self.hit is not None or type(tiles)is not int or tiles<0:raise ValueError('invalid experimental advance')
        try:
            require_current(self.job,self.current);self.cursor.stop=min(self.plan.count,self.cursor.next_tile+tiles)
            while self.cursor.next_tile<self.cursor.stop:
                first=self.cursor.next_tile;stop=min(self.cursor.stop,first+self.backend.dispatch.limit)
                if self.mode.startswith('panel'):
                    _,column,width,local=layout(self.plan,self.mode,first);stop=min(stop,first+len(self.plan.rows)*width-local)
                batch=Batch(self.plan,first,stop);require_current(self.job,self.current)
                result=self.backend(batch,1,self.job.generation);require_current(self.job,self.current)
                if result.overflow:
                    self.cursor.retries+=1;result=self.backend(batch,stop-first,self.job.generation);require_current(self.job,self.current)
                records=result.require_complete()
                if result.total!=len(records):raise ValueError('incomplete experimental candidate queue')
                if records:
                    index=min(records);self.hit=Hit(self.job.generation,canonical(self.plan,self.mode,first+index),records[index])
                require_current(self.job,self.current);self.cursor.next_tile=stop;self.cursor.batches_done+=1
                if self.hit is not None:break
            self.cursor.status='complete'if self.cursor.next_tile==self.cursor.stop else 'running'
            return self.hit,self.cursor
        except BaseException:self.close();raise


def new_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='wide16k'):
    if mode not in MODES:raise ValueError('unknown experiment')
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident maps required')
    plan=geometry.plan;group=16 if mode.startswith('small')else 32
    if len(plan.rows)%4 or (len(plan.rows)>group and len(plan.rows)%group):raise ValueError('unsupported experimental row count')
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        backend=BACKENDS[mode](profile,actual,plan=plan,bound=bound,current_generation=generation,on_close=on_close,tables_factory=tables_factory)
        backend.dispatch.check_current=lambda:require_current(context.job,current)
        return backend
    return Search(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan,mode=mode)
