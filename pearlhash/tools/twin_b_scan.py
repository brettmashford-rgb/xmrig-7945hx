"""v082 bounded two-nonce experiment; independent A/keys/queues, shared job B/maps. ISC."""
import ctypes as C
from pool.search import Nonce,require_current
from tools.job_b_tables import JobBTables
from tools.job_geometry import JobGeometry
from tools.pair_depth_scan import new_search,Batch,canonical
from tools.virtual_scan import table_payload

MODES=('pair-direct','twin-private-b','twin-shared-b')
ENTRIES={'twin-private-b':b'twin_private_b_scan','twin-shared-b':b'twin_shared_b_scan'}
LIMIT=16384


def validate_pair(contexts,current):
    if type(contexts)is not tuple or len(contexts)!=2 or any(type(c)is not Nonce for c in contexts):
        raise ValueError('exactly two prepared immutable nonces required')
    a,b=contexts
    for c in contexts:require_current(c.job,current)
    if a.job is not b.job or a.base!=b.base:raise ValueError('nonces must belong to the same current job/base')
    if (a.worker,a.miner)==(b.worker,b.miner) or a.root_a==b.root_a or a.profile.seed_a==b.profile.seed_a or a.profile.tail==b.profile.tail:
        raise ValueError('distinct nonce, root, A seed and tail required')
    fields=('m','n','k','rank','fill','seed_b')
    if any(getattr(a.profile,f)!=getattr(b.profile,f)for f in fields):raise ValueError('B reconstruction binding differs')


class SharedOwner:
    """Only this coordinator shares immutable inputs; underlying owner stays leased."""
    def __init__(self,owner,geometry=False):self.owner=owner;self.geometry=geometry;self.users=0
    def view(self):return OwnerView(self)


class OwnerView:
    def __init__(self,pool):self.pool=pool;self.leased=False
    def __getattr__(self,name):return getattr(self.pool.owner,name)
    def acquire(self,*args):
        o=self.pool.owner
        if self.leased or o.closed:raise ValueError('busy or closed immutable view')
        if self.pool.geometry:o.validate(*args)
        else:
            device,p=args;table_payload(p)
            if device is not o.device or (p.m,p.n,p.k,p.rank,p.fill,p.seed_b)!=o.binding:
                raise ValueError('foreign B view')
        if not self.pool.users:o.acquire(*args)
        self.pool.users+=1;self.leased=True
    def release(self):
        if not self.leased:raise ValueError('view already released')
        self.leased=False;self.pool.users-=1
        if not self.pool.users:self.pool.owner.release()


class JobInputs:
    def __init__(self,device,context,current):
        self.b=self.geometry=None;self.closed=False
        try:
            self.b=JobBTables(device,context,current)
            self.geometry=JobGeometry(device,context.job,current,maps=True)
            self.b_pool=SharedOwner(self.b);self.geometry_pool=SharedOwner(self.geometry,True)
        except BaseException:self.close();raise
    def close(self):
        if self.closed:return
        error=None
        for o in (self.geometry,self.b):
            if o is not None:
                try:o.close()
                except BaseException as exc:error=error or exc
        if error is not None:raise error
        self.closed=True


class Twin:
    """No pool IO or automatic promotion. A scan credits both domains only after completion."""
    def __init__(self,contexts,device,current,inputs):
        validate_pair(contexts,current)
        if inputs.closed:raise ValueError('closed shared inputs')
        self.contexts=contexts;self.device=device;self.current=current;self.inputs=inputs
        self.searches=[];self.closed=False;self.functions={};self.last_traces=None
        self.completed_unique_tiles=0;self.retries=0
        try:
            for context in contexts:
                self.searches.append(new_search(context,device,current,inputs.b_pool.view(),inputs.geometry_pool.view(),mode='pair-direct'))
            self.dispatches=tuple(s.backend.dispatch for s in self.searches);self.plan=self.searches[0].plan
            for mode,entry in ENTRIES.items():
                f=C.c_void_p();device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],C.byref(f),device.module,entry)
                self.functions[mode]=f
            a,b=self.dispatches
            # Immutable B, maps and dimensions must be the actual same device inputs.
            if any(a.arguments[i].value!=b.arguments[i].value for i in (1,3,5,14,15,16,17,18,20,21,22)):
                raise ValueError('fused inputs do not share identical B/maps/profile')
            if a.arguments[0].value==b.arguments[0].value or a.arguments[7].value==b.arguments[7].value:
                raise ValueError('nonce-specific A/key alias')
            self.arguments=a.arguments+(b.arguments[0],b.arguments[7],b.status[1],b.queue[1],b.trace[1])
            self.params=(C.c_void_p*len(self.arguments))(*(C.cast(C.byref(v),C.c_void_p)for v in self.arguments))
        except BaseException:self.close();raise

    def check(self):
        if self.closed:raise ValueError('closed two-nonce experiment')
        for context in self.contexts:require_current(context.job,self.current)

    def scan(self,mode,first,count,*,capacity=0,audit=False):
        if mode not in MODES:raise ValueError('unknown two-nonce mode')
        ds=self.dispatches;generation=self.contexts[0].job.generation
        try:
            self.check()
            batches=tuple(Batch(self.plan,first,first+count)for d in ds)
            prepared=tuple(d.prepare_window(b)for d,b in zip(ds,batches))
            if ds[0].bound!=ds[1].bound:raise ValueError('nonce targets differ')
            for d,b,p in zip(ds,batches,prepared):
                d.require_open();d.validate_window(b,p,generation,capacity,audit)
                if d.pending or d.loaded is not None:raise ValueError('nonce stream already owns work')
            if mode=='pair-direct':
                results=[];traces=[]
                for d,b,p in zip(ds,batches,prepared):
                    self.check()
                    results.append(d.scan_window(b,p,generation,capacity=capacity,audit=audit,current=lambda:generation if self.current(self.contexts[0].job)else generation^1))
                    traces.append(self.device.last_transcripts)
            else:
                a,b=ds
                for d,p in zip(ds,prepared):
                    d.audit.value=int(audit);d.queue_capacity.value=capacity;d.count.value=count
                    d.generation.value=generation;d.first.value=first
                    d.snapshot_ready=False;d.snapshot_enqueued=False
                    d.loaded=(p,generation,capacity,audit);d.launched=False
                # The first stream owns all work, including both guard collectors.
                a.pending=True
                for d in ds:
                    self.device.api('cuMemsetD32Async',[C.c_ulonglong,C.c_uint,C.c_size_t,C.c_void_p],d.status[1],0,2,a.stream)
                self.check()
                self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                    self.functions[mode],a.grid(count,first),1,1,512,1,1,0,a.stream,self.params,None)
                for d in ds:
                    d.launched=True
                    self.device.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                        d.collector,(d.snapshot[2]+127)//128,1,1,128,1,1,0,a.stream,d.snapshot_params,None)
                    d.snapshot_enqueued=True
                a.wait();self.check()
                finished=[d.finish()for d in ds]
                results=[r for r,t in finished];traces=[t for r,t in finished]
            self.check();self.last_traces=tuple(traces)
            return tuple(results)
        except BaseException:
            self.close();raise
        finally:
            for d in ds:d.snapshot_ready=False

    def complete_scan(self,mode,first,count,*,audit=False):
        results=self.scan(mode,first,count,capacity=1,audit=audit)
        if any(r.overflow for r in results):
            self.retries+=1;results=self.scan(mode,first,count,capacity=count,audit=audit)
        for r in results:r.require_complete()
        return results

    def run(self,mode,first,stop):
        if any(type(x)is not int for x in(first,stop))or not 0<=first<stop<=self.plan.count:raise ValueError('invalid work interval')
        begin=first
        while first<stop:
            count=min(LIMIT,stop-first);results=self.scan(mode,first,count)
            if any(r.total for r in results):raise RuntimeError('unexpected tiny-target benchmark candidate')
            first+=count;self.completed_unique_tiles+=2*count
        return begin,stop

    def close(self):
        if self.closed:return
        error=None
        for s in self.searches:
            try:s.close()
            except BaseException as exc:error=error or exc
        if error is not None:raise error
        self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
