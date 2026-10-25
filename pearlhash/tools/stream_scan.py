"""Offline split-phase dispatch; shared read-only A/noise, private queues. ISC."""
import ctypes as C
import struct
from tools.prepared_dispatch import PreparedDispatch, PreparedBatch
from tools.wide_scan import validate_wide, decode_wide
from tools.virtual_scan import global_reference
from tools.candidate_scan import verify_returned


class StreamDispatch(PreparedDispatch):
    def __init__(self,*args,**kwargs):
        self.stream=C.c_void_p();self.pending=False;self.loaded=None;self.launched=False
        super().__init__(*args,**kwargs)
        try:self.device.api('cuStreamCreate',[C.POINTER(C.c_void_p),C.c_uint],C.byref(self.stream),1)
        except BaseException:self.close();raise

    def stage(self,batch,generation,*,capacity=None,audit=False):
        self.require_open()
        if self.pending:raise ValueError('stream still owns an unfinished batch')
        if not isinstance(batch,PreparedBatch)or batch.owner is not self.token:raise ValueError('foreign prepared batch')
        capacity=self.capacity if capacity is None else capacity
        validate_wide(batch.bounds,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('invalid stream dispatch options')
        self.loaded=None
        self.upload(self.desc[1],batch.descriptors);self.upload(self.targets[1],batch.targets)
        self.upload(self.status[1],bytes(8))
        self.audit.value=int(audit);self.queue_capacity.value=capacity
        self.count.value=len(batch.queries);self.generation.value=generation
        self.loaded=(batch,generation,capacity,audit);self.launched=False

    def enqueue(self):
        self.require_open()
        if self.loaded is None or self.pending or self.launched:raise ValueError('stage a fresh batch before enqueue')
        self.pending=True;self.launched=True
        self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
            self.function,(self.count.value+7)//8,1,1,256,1,1,0,self.stream,self.params,None)

    def wait(self):
        if self.pending:
            self.device.api('cuStreamSynchronize',[C.c_void_p],self.stream)
            self.pending=False

    def finish(self):
        if self.loaded is None or not self.launched:raise ValueError('no launched batch')
        self.wait();batch,generation,capacity,audit=self.loaded
        # This is called only after both streams have waited in the benchmark,
        # so synchronous readback/guard checks cannot serialize their launches.
        result=decode_wide(self.download(self.queue,capacity*44),self.download(self.status,8),batch.bounds,capacity,generation)
        raw=self.download(self.trace,len(batch.queries)*64 if audit else 0)
        traces=tuple(struct.unpack_from('<16I',raw,i*64)for i in range(len(batch.queries)))if audit else None
        self.check_buffer(self.desc);self.check_buffer(self.targets);self.tables.check_guards()
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

    def run(self,*args,**kwargs):
        raise ValueError('use stage/enqueue/wait/finish for offline streams')

    def close(self):
        if self.closed:return
        self.wait()
        if self.stream.value:
            self.device.api('cuStreamDestroy_v2',[C.c_void_p],self.stream);self.stream=C.c_void_p()
        super().close()


def execute_pair(lanes,batches,generation,parallel,*,capacity=0,audit=False):
    """Load before launch; no upload, allocation or readback between paired launches."""
    for lane,batch in zip(lanes,batches):lane.stage(batch,generation,capacity=capacity,audit=audit)
    lanes[0].device.api('cuCtxSynchronize',[])
    if parallel:
        for lane in lanes:lane.enqueue()
        for lane in lanes:lane.wait()
    else:
        for lane in lanes:lane.enqueue();lane.wait()
    return tuple(lane.finish()for lane in lanes)
