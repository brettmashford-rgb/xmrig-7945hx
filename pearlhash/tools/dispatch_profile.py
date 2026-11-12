"""Separate instrumented baseline host/API/event profile; never timing samples. ISC."""
from collections import defaultdict
import ctypes as C,time


def profile_control(search,windows=32):
    d=search.backend.dispatch;device=d.device;original=device.api;events=[]
    buckets=defaultdict(float);counts=defaultdict(int);instrumentation=[0.];elapsed=0.;wall=0.
    def event_record(event):
        before=time.perf_counter();original('cuEventRecord',[C.c_void_p,C.c_void_p],event,d.stream)
        instrumentation[0]+=time.perf_counter()-before
    def wrapped(name,types,*args):
        scanner=name=='cuLaunchKernel'and args[0].value==d.function.value
        if scanner:event_record(events[0])
        before=time.perf_counter()
        try:return original(name,types,*args)
        finally:
            label={'cuMemsetD32Async':'reset','cuLaunchKernel':'launch','cuStreamSynchronize':'wait','cuMemcpyDtoH_v2':'readback'}.get(name,'other')
            buckets[label]+=time.perf_counter()-before;counts[name]+=1
            if scanner:event_record(events[1])
    try:
        for _ in range(2):
            event=C.c_void_p();original('cuEventCreate',[C.POINTER(C.c_void_p),C.c_uint],C.byref(event),0);events.append(event)
        for i in range(windows):
            device.api=wrapped;before=time.perf_counter()
            first=search.cursor.next_tile
            try:hit,cursor=search.advance(16384)
            finally:wall+=time.perf_counter()-before;device.api=original
            if hit is not None or cursor.next_tile!=first+16384:raise RuntimeError('unexpected hit or incomplete profile window')
            value=C.c_float();original('cuEventElapsedTime',[C.POINTER(C.c_float),C.c_void_p,C.c_void_p],C.byref(value),*events)
            if value.value<=0:raise RuntimeError('invalid scanner event interval')
            elapsed+=value.value/1000.
        if sum(buckets.values())+instrumentation[0]>wall+1e-6:raise RuntimeError('profile buckets overlap')
        return dict(windows=windows,tiles=windows*16384,wall_seconds=wall,host_api_seconds=dict(buckets),api_counts=dict(counts),
            event_instrumentation_seconds=instrumentation[0],python_and_bookkeeping_seconds=max(0.,wall-sum(buckets.values())-instrumentation[0]),
            scanner_event_seconds=elapsed,
            clock_note='GPU events overlap host waits; do not add GPU and host buckets. Events can include scheduling/submission gaps; not instruction cycles or achieved utilization.',
            scope='separate instrumented pair-direct diagnostic; excluded from throughput and energy samples')
    finally:
        device.api=original
        d.wait()
        for event in events:original('cuEventDestroy_v2',[C.c_void_p],event)
