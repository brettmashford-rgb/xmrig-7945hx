"""Nonce-owned reusable virtual backend for the existing global range engine. ISC."""
import time

from tools.prepared_dispatch import PreparedDispatch,KERNELS
from tools.production_scan import ProductionCandidateScanner,require_production
from tools.virtual_scan import VirtualTables,table_payload
from tools.wide_scan import WideBatch,validate_wide


class PreparedCandidateBackend:
    def __init__(self,profile,device,*,bound,current_generation=None,on_close=None):
        table_payload(profile);require_production(profile,())
        validate_wide([bound],1,0)
        if not isinstance(device,ProductionCandidateScanner):
            raise ValueError('production GPU scanner required; no CPU fallback')
        self.profile=profile;self.device=device;self.bound=bound
        self.current_generation=current_generation;self.on_close=on_close
        self.tables=None;self.dispatch=None;self.closed=False
        self.batch=None;self.prepared=None;self.generation=None
        self.preparations=0;self.dispatches=0;self.prepare_seconds=0.;self.scan_seconds=0.
        self.buffer_allocations=0;self.buffer_bytes=0
        try:
            self.tables=VirtualTables(device,profile)
            self.dispatch=PreparedDispatch(device,self.tables,KERNELS[0])
            self.buffer_allocations=len(self.dispatch.owned)
            self.buffer_bytes=sum(buffer[2]+32 for buffer in self.dispatch.buffers)
        except BaseException:
            self.close();raise

    def __call__(self,batch,capacity,generation):
        if self.closed or not isinstance(batch,WideBatch):
            raise ValueError('open reusable backend and wide batch required')
        validate_wide([self.bound]*len(batch.maps),capacity,generation)
        if self.generation is not None and self.generation!=generation:
            raise ValueError('nonce backend cannot change generation')
        if self.current_generation is not None and self.current_generation()!=generation:
            raise ValueError('nonce backend generation is not current')
        self.generation=generation
        if batch!=self.batch:
            self.batch=None;self.prepared=None
            started=time.monotonic()
            prepared=self.dispatch.prepare(batch.queries(),[self.bound]*len(batch.maps))
            self.prepare_seconds+=time.monotonic()-started
            self.batch=batch;self.prepared=prepared;self.preparations+=1
        started=time.monotonic()
        try:
            result=self.dispatch.run(self.prepared,generation,capacity=capacity,current=self.current_generation)
        finally:self.scan_seconds+=time.monotonic()-started
        self.dispatches+=1
        return result

    def stats(self):
        return {'prepared_batches':self.preparations,'dispatches':self.dispatches,
                'prepare_seconds':self.prepare_seconds,'scan_seconds':self.scan_seconds,
                'dispatch_buffer_allocations':self.buffer_allocations,
                'dispatch_buffer_bytes':self.buffer_bytes,'closed':self.closed}

    def close(self):
        if not self.closed:
            self.closed=True
            try:
                if self.dispatch is not None:self.dispatch.close()
            finally:
                if self.tables is not None:self.tables.close()
                self.batch=None;self.prepared=None
            if self.on_close is not None:self.on_close(self.stats())
