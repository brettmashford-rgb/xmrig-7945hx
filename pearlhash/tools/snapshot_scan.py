"""Same-window status and every guard in one readback; offline only. ISC."""
import ctypes as C
import struct
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.resident_scan import ResidentDispatch,ResidentBackend
from tools.direct_resident import DirectDispatch
from tools.stream_scan import populated_count
from tools.wide_scan import decode_wide
from tools.virtual_scan import global_reference
from tools.candidate_scan import verify_returned
from tools.prepared_dispatch import GUARD


class SnapshotMixin:
    def __init__(self,device,tables,cache,plan,bound):
        self.snapshot_ready=False;self.snapshot_enqueued=False
        super().__init__(device,tables,cache,plan,bound)
        try:
            # Seven original dispatch buffers, four noise buffers and A cache.
            noise=[]
            for raw,u,praw,p,rows in tables.buffers.values():
                noise.extend(((raw,u,rows*tables.profile.rank),(praw,p,tables.profile.k*4)))
            original=tuple(self.buffers)+tuple(noise)+((cache.raw,cache.pointer,cache.bytes),)
            self.guard_count=2*(len(original)+2)
            if not 1<=self.guard_count<=64:raise ValueError('snapshot guard cap exceeded')
            self.addresses=self.guarded(self.guard_count*8)
            self.snapshot=self.guarded(24+self.guard_count*16)
            covered=original+(self.addresses,self.snapshot)
            self.guard_addresses=tuple(address for raw,pointer,size in covered
                for address in (raw.value,raw.value+size+16))
            self.covered={raw.value for raw,pointer,size in covered}
            self.upload(self.addresses[1],struct.pack('<'+'Q'*self.guard_count,*self.guard_addresses))
            self.collector=C.c_void_p()
            device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                C.byref(self.collector),device.module,b'resident_guard_snapshot')
            self.snapshot_args=(self.addresses[1],self.status[1],self.snapshot[1],C.c_uint(self.guard_count),
                self.generation,self.first,self.count)
            self.snapshot_params=(C.c_void_p*len(self.snapshot_args))(
                *(C.cast(C.byref(v),C.c_void_p)for v in self.snapshot_args))
            device.api('cuCtxSynchronize',[])
        except BaseException:self.close();raise

    def scan_window(self,*args,**kwargs):
        self.snapshot_ready=False;self.snapshot_enqueued=False
        try:return super().scan_window(*args,**kwargs)
        finally:self.snapshot_ready=False

    def wait(self):
        if self.pending and self.loaded is not None and not self.snapshot_enqueued:
            self.snapshot_enqueued=True
            self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                self.collector,(self.snapshot[2]+127)//128,1,1,128,1,1,0,self.stream,self.snapshot_params,None)
        super().wait()

    def check_buffer(self,buffer):
        if self.snapshot_ready:
            if buffer[0].value not in self.covered:raise ValueError('buffer absent from snapshot')
        else:super().check_buffer(buffer)

    def finish(self):
        if self.loaded is None or not self.launched:raise ValueError('no launched batch')
        self.wait();batch,generation,capacity,audit=self.loaded
        # Includes the collector's own output guards. Validate before using status.
        raw=self.tables.read(self.snapshot[0],0,self.snapshot[2]+32)
        if (raw[:16]!=GUARD or raw[-16:]!=GUARD
                or raw[40:-16]!=GUARD*self.guard_count):
            raise RuntimeError('snapshot guard changed')
        if raw[24:40]!=struct.pack('<QII',generation,self.first.value,len(batch.queries)):
            raise RuntimeError('stale snapshot window identity')
        self.snapshot_ready=True;status=raw[16:24]
        count=populated_count(status,batch.bounds,capacity,generation)
        # Queue/transcript copies occur only when populated/requested, after all guards.
        records=self.tables.read(self.queue[1],0,count*44)if count else b''
        result=decode_wide(records,status,batch.bounds,count,generation)
        words=self.tables.read(self.trace[1],0,len(batch.queries)*64)if audit else b''
        traces=tuple(struct.unpack_from('<16I',words,i*64)for i in range(len(batch.queries)))if audit else None
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


class SnapshotResidentDispatch(SnapshotMixin,ResidentDispatch):pass
class SnapshotDirectDispatch(SnapshotMixin,DirectDispatch):pass
class SnapshotResidentBackend(ResidentBackend):dispatch_type=SnapshotResidentDispatch
class SnapshotDirectBackend(ResidentBackend):dispatch_type=SnapshotDirectDispatch


def new_snapshot_search(context,device,current,*,direct=False,start=0,on_close=None):
    if type(direct)is not bool:raise ValueError('boolean direct selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        backend=SnapshotDirectBackend if direct else SnapshotResidentBackend
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
