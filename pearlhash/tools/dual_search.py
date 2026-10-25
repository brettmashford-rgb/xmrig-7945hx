"""Two-stream cached-A nonce search with atomic pair cursor credit. ISC."""
import time
from pool.search import NonceSearch,Hit,require_current
from tools.fast_plan import FastPlan,FastBatch
from tools.cached_a import CachedA,attach
from tools.stream_scan import StreamDispatch
from tools.prepared_dispatch import KERNELS
from tools.production_scan import ProductionCandidateScanner
from tools.virtual_scan import VirtualTables,table_payload
from tools.wide_scan import validate_wide


def intervals(first,stop):
    if any(type(v)is not int for v in(first,stop))or not 0<=first<stop or stop-first>8192:
        raise ValueError('expected one bounded pair interval')
    middle=first+(stop-first+1)//2
    return ((first,middle),(middle,stop))if middle<stop else((first,stop),)


class DualBackend:
    def __init__(self,profile,device,*,plan,bound,current_generation=None,on_close=None):
        if (not isinstance(device,ProductionCandidateScanner)or type(plan)is not FastPlan
                or plan.profile!=(profile.m,profile.n,profile.k,profile.rank,profile.fill)):
            raise ValueError('production scanner and matching immutable plan required')
        table_payload(profile);validate_wide([bound],1,0)
        self.device=device;self.plan=plan;self.bound=bound;self.current_generation=current_generation
        self.on_close=on_close;self.closed=False;self.tables=None;self.cache=None;self.lanes=[]
        self.generation=None;self.preparations=0;self.dispatches=0;self.pairs=0
        self.prepare_seconds=0.;self.scan_seconds=0.;self.buffer_allocations=0;self.buffer_bytes=0
        try:
            self.tables=VirtualTables(device,profile);self.cache=CachedA(self.tables)
            for _ in range(2):
                lane=StreamDispatch(device,self.tables,KERNELS[0]);self.lanes.append(lane);attach(lane,self.cache)
                self.buffer_allocations+=len(lane.owned)
                self.buffer_bytes+=sum(buf[2]+32 for buf in lane.buffers)
        except BaseException:self.close();raise

    def current(self,generation):
        if self.closed:raise ValueError('closed dual backend')
        if self.generation is not None and self.generation!=generation:raise ValueError('nonce generation changed')
        if self.current_generation is not None and self.current_generation()!=generation:raise ValueError('stale generation')

    def scan(self,first,stop,generation):
        self.current(generation);self.generation=generation
        spans=intervals(first,stop)
        if stop>self.plan.count:raise ValueError('pair outside canonical domain')
        started=time.monotonic()
        batches=[self.plan.prepare(lane.token,FastBatch(self.plan,a,b),self.bound,4096)
                 for lane,(a,b)in zip(self.lanes,spans)]
        self.prepare_seconds+=time.monotonic()-started;self.preparations+=len(batches)
        active=self.lanes[:len(batches)];started=time.monotonic()
        try:
            for lane,batch in zip(active,batches):lane.stage(batch,generation,capacity=len(batch.queries))
            self.device.api('cuCtxSynchronize',[]);self.current(generation)
            # Never allocate, upload, read back, or synchronize the context
            # between these enqueues. Arguments/buffers belong to each lane.
            for lane in active:
                self.current(generation);lane.enqueue()
            for lane in active:lane.wait()
            self.current(generation)
            records=[]
            for lane,(a,b)in zip(active,spans):
                result,_=lane.finish();self.current(generation)
                complete=result.require_complete()
                if result.total!=len(complete):raise ValueError('incomplete stream result')
                records.extend((a+i,digest)for i,digest in complete.items())
            self.current(generation);self.dispatches+=len(active);self.pairs+=1
            return tuple(sorted(records))
        except BaseException:
            self.scan_seconds+=time.monotonic()-started
            self.close();raise
        finally:
            if not self.closed:self.scan_seconds+=time.monotonic()-started

    def stats(self):
        return {'prepared_batches':self.preparations,'dispatches':self.dispatches,'stream_pairs':self.pairs,
                'prepare_seconds':self.prepare_seconds,'scan_seconds':self.scan_seconds,
                'dispatch_buffer_allocations':self.buffer_allocations,'dispatch_buffer_bytes':self.buffer_bytes,
                'a_cache_bytes':self.cache.bytes if self.cache is not None else 0,
                'a_cache_seconds':getattr(self.cache,'setup_seconds',0.),'closed':self.closed}

    def close(self):
        if self.closed:return
        self.closed=True;error=None
        # Finish every outstanding kernel before releasing either shared cache.
        for lane in self.lanes:
            try:lane.wait()
            except BaseException as exc:error=error or exc
        for resource in [*self.lanes,self.cache,self.tables]:
            if resource is not None:
                try:resource.close()
                except BaseException as exc:error=error or exc
        if self.on_close is not None:self.on_close(self.stats())
        if error is not None:raise error


class DualSearch(NonceSearch):
    def __init__(self,context,device,current,*,start=0,on_close=None):
        require_current(context.job,current);plan=FastPlan.from_job(context.job)
        def generation():require_current(context.job,current);return context.job.generation
        def factory(profile,device,*,bound):
            return DualBackend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
        super().__init__(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)

    def advance(self,tiles):
        if self.closed or self.hit is not None:raise ValueError('search closed or candidate already found')
        if type(tiles)is not int or tiles<0:raise ValueError('invalid search window size')
        try:
            require_current(self.job,self.current)
            self.cursor.stop=min(self.plan.count,self.cursor.next_tile+tiles)
            while self.cursor.next_tile<self.cursor.stop:
                first=self.cursor.next_tile;stop=min(first+8192,self.cursor.stop)
                records=self.backend.scan(first,stop,self.job.generation)
                require_current(self.job,self.current)
                # Only a complete validated current pair earns cursor credit.
                if records:
                    tile,digest=records[0]
                    self.hit=Hit(self.job.generation,tile,digest)
                self.cursor.next_tile=stop;self.cursor.batches_done+=len(intervals(first,stop))
                self.cursor.status='complete'if stop==self.cursor.stop else'running'
                if self.hit is not None:break
            require_current(self.job,self.current)
            return self.hit,self.cursor
        except BaseException:
            self.cursor.status='cancelled';self.close();raise
