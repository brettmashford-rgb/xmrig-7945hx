"""One guarded B-noise owner per job/device; exclusive per-nonce leases. ISC."""
import ctypes as C
import time
from pool.search import require_current
from tools.virtual_scan import VirtualTables,table_payload
from tools.shared_b_scan import SharedBBackend,RowPairSearch,require_pair_plan
from tools.fast_plan import FastPlan


class JobBTables:
    def __init__(self,device,context,current):
        require_current(context.job,current)
        p=context.profile;table_payload(p)
        self.device=device;self.job_key=context.job.job_key
        self.binding=(p.m,p.n,p.k,p.rank,p.fill,p.seed_b)
        self.profile=p;self.closed=False;self.leased=False;self.owned=[];self.checked=set()
        self.leases=0;self.generated_bytes=p.n*p.rank+p.k*4
        started=time.monotonic()
        try:
            self.key_b=self.allocate(p.seed_b)
            raw,u=self.guarded(p.n*p.rank);praw,perm=self.guarded(p.k*4)
            self.buffer=(raw,u,praw,perm,p.n)
            blocks=p.n*p.rank//32;domain=C.c_uint(int.from_bytes(b'B_te','little'))
            device.launch(b'noise_uniform_range',(self.key_b,u,C.c_uint(0),C.c_uint(blocks),domain),(blocks+127)//128,128)
            device.launch(b'noise_permutation',(self.key_b,perm,C.c_uint(p.k),C.c_uint(p.rank),domain),(p.k//8+127)//128,128)
            device.api('cuCtxSynchronize',[]);self.check_guards();require_current(context.job,current)
            self.setup_seconds=time.monotonic()-started
        except BaseException:self.close();raise

    allocate=VirtualTables.allocate
    guarded=VirtualTables.guarded
    read=VirtualTables.read

    def check_guards(self):
        if self.closed:raise ValueError('closed job B tables')
        raw,u,praw,perm,rows=self.buffer
        for pointer,size in ((raw,rows*self.profile.rank),(praw,self.profile.k*4)):
            if self.read(pointer,0,16)!=b'\xa5'*16 or self.read(pointer,size+16,16)!=b'\xa5'*16:
                raise RuntimeError('job B table guard changed')

    def validate_context(self,context,current):
        require_current(context.job,current)
        p=context.profile
        if self.closed or context.job.job_key!=self.job_key or (p.m,p.n,p.k,p.rank,p.fill,p.seed_b)!=self.binding:
            raise ValueError('foreign or closed job B tables')

    def acquire(self,device,profile):
        table_payload(profile)
        if (self.closed or self.leased or device is not self.device
                or (profile.m,profile.n,profile.k,profile.rank,profile.fill,profile.seed_b)!=self.binding):
            raise ValueError('foreign, busy or closed job B table lease')
        self.check_guards();self.leased=True;self.leases+=1

    def release(self):
        if not self.leased:raise ValueError('job B lease already released')
        self.leased=False

    def close(self):
        if self.closed:return
        if self.leased:raise ValueError('cannot free leased job B tables')
        self.closed=True
        for pointer in reversed(self.owned):self.device.release(pointer)
        self.owned.clear()

    def stats(self):
        return dict(b_table_builds=1,b_table_leases=self.leases,b_table_generated_bytes=self.generated_bytes,
            b_table_setup_seconds=getattr(self,'setup_seconds',0.),closed=self.closed)


def new_job_b_search(context,device,current,owner,*,start=0,on_close=None):
    owner.validate_context(context,current)
    plan=FastPlan.from_job(context.job);require_pair_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def tables_factory(actual,profile):
        owner.validate_context(context,current)
        return VirtualTables(actual,profile,b_cache=owner)
    def factory(profile,actual,*,bound):
        return SharedBBackend(profile,actual,plan=plan,bound=bound,current_generation=generation,
            on_close=on_close,tables_factory=tables_factory)
    return RowPairSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
