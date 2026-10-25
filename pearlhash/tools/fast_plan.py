"""Immutable validated pattern axes and lazy global queries. ISC license.

Only descriptor planning changes. Original global row-major tile IDs are kept.
Every axis is generated, bounds/type checked and serialized once per plan. Batch
checks are interval checks into that immutable plan, not arbitrary trusted input.
"""
from dataclasses import dataclass
import struct
import time

from reference.tile_ranges import PatternDomain
from reference.patterns import PeriodicPattern
from tools.check_tile_scan_gpu import TileQuery
from tools.prepared_dispatch import PreparedBatch
from tools.prepared_backend import PreparedCandidateBackend
from tools.wide_scan import validate_wide


@dataclass(frozen=True)
class Axis:
    indices:tuple
    packed:bytes


def axes(dimension,pattern,expected):
    domain=PatternDomain(dimension,pattern)
    if pattern.size!=expected or not domain.count or domain.count>(512 if expected==10 else 16384):
        raise ValueError('production pattern shape or domain differs')
    result=[]
    for i in range(domain.count):
        indices=domain.indices(i)
        if (type(indices)is not tuple or len(indices)!=expected
                or any(type(v)is not int or not 0<=v<dimension or v>0xffffffff for v in indices)):
            raise ValueError('invalid generated global indices')
        result.append(Axis(indices,struct.pack('<32I',*indices,*([0]*(32-expected)))))
    return tuple(result)


@dataclass(frozen=True)
class FastPlan:
    rows:tuple
    cols:tuple
    prefixes:tuple
    profile:tuple
    count:int
    patterns:tuple

    @classmethod
    def from_job(cls,job):
        p=job.profile
        if (p.k,p.rank)!=(32768,128):raise ValueError('production K32768/rank128 required')
        # Snapshot the validated domains; no mutable PatternDomain is retained.
        ra=axes(p.m,p.rows,10);cb=axes(p.n,p.cols,16)
        if len(ra)>512 or len(cb)>16384:
            raise ValueError('production planning axis cap exceeded')
        return cls(ra,cb,tuple(struct.pack('<2I',10,16)+row.packed for row in ra),
                   (p.m,p.n,p.k,p.rank,64),len(ra)*len(cb),(p.rows.encoded,p.cols.encoded))

    def __post_init__(self):
        # Plans must be built by from_job; also validate public direct creation.
        if (type(self.rows)is not tuple or type(self.cols)is not tuple or not self.rows or not self.cols
                or len(self.rows)>512 or len(self.cols)>16384
                or type(self.profile)is not tuple or len(self.profile)!=5
                or any(type(v)is not int for v in self.profile)
                or self.profile[2:]!=(32768,128,64)
                or type(self.count)is not int or self.count!=len(self.rows)*len(self.cols)
                or type(self.prefixes)is not tuple or len(self.prefixes)!=len(self.rows)
                or type(self.patterns)is not tuple or len(self.patterns)!=2
                or any(type(p)is not bytes or len(p)!=6 for p in self.patterns)):
            raise ValueError('invalid immutable production plan')
        for side,(entries,limit,shape)in enumerate(((self.rows,self.profile[0],10),(self.cols,self.profile[1],16))):
            domain=PatternDomain(limit,PeriodicPattern(self.patterns[side]))
            if domain.count!=len(entries):raise ValueError('canonical axis count differs')
            for i,entry in enumerate(entries):
                if (type(entry)is not Axis or type(entry.indices)is not tuple or len(entry.indices)!=shape
                        or any(type(v)is not int or not 0<=v<limit or v>0xffffffff for v in entry.indices)
                        or entry.indices!=domain.indices(i)
                        or type(entry.packed)is not bytes or entry.packed!=struct.pack('<32I',*entry.indices,*([0]*(32-shape)))):
                    raise ValueError('axis bounds or descriptor differs')
                if side==0 and self.prefixes[i]!=struct.pack('<2I',10,16)+entry.packed:
                    raise ValueError('row descriptor prefix differs')

    def indices(self,tile):
        if type(tile)is not int or not 0<=tile<self.count:raise ValueError('global tile ID outside plan')
        a,b=divmod(tile,len(self.cols));return self.rows[a].indices,self.cols[b].indices

    def batches(self,start,stop):
        if any(type(v)is not int for v in(start,stop))or not 0<=start<=stop<=self.count:
            raise ValueError('invalid fast plan interval')
        for first in range(start,stop,4096):yield FastBatch(self,first,min(first+4096,stop))

    def prepare(self,owner,batch,bound,capacity):
        if type(batch)is not FastBatch or batch.plan is not self:raise ValueError('foreign fast batch')
        count=batch.stop-batch.start
        validate_wide([bound],capacity,0)
        chunks=[];position=batch.start;n=len(self.cols)
        while position<batch.stop:
            row,col=divmod(position,n);length=min(n-col,batch.stop-position)
            prefix=self.prefixes[row]
            chunks.extend(prefix+self.cols[b].packed for b in range(col,col+length))
            position+=length
        return PreparedBatch(owner,Queries(batch),b''.join(chunks),(bound,)*count,
                             bound.to_bytes(32,'little')*count)


@dataclass(frozen=True)
class FastBatch:
    plan:FastPlan
    start:int
    stop:int

    def __post_init__(self):
        if (type(self.plan)is not FastPlan or any(type(v)is not int for v in(self.start,self.stop))
                or not 0<=self.start<self.stop<=self.plan.count or self.stop-self.start>4096):
            raise ValueError('invalid validated batch interval')

    @property
    def maps(self):return Maps(self)

    def queries(self):return Queries(self)


@dataclass(frozen=True)
class Maps:
    batch:FastBatch
    def __len__(self):return self.batch.stop-self.batch.start
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i]for i in range(*index.indices(len(self))))
        if type(index)is not int:raise TypeError('integer query index required')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        return self.batch.plan.indices(self.batch.start+index)


class Queries(Maps):
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i]for i in range(*index.indices(len(self))))
        return TileQuery(*super().__getitem__(index))


class FastCandidateBackend(PreparedCandidateBackend):
    def __init__(self,profile,device,*,plan,bound,current_generation=None,on_close=None):
        if type(plan)is not FastPlan or plan.profile!=(profile.m,profile.n,profile.k,profile.rank,profile.fill):
            raise ValueError('plan and nonce profile differ')
        self.plan=plan
        super().__init__(profile,device,bound=bound,current_generation=current_generation,on_close=on_close)

    def __call__(self,batch,capacity,generation):
        if self.closed or type(batch)is not FastBatch or batch.plan is not self.plan:
            raise ValueError('open backend and its own validated plan required')
        validate_wide([self.bound],capacity,generation)
        if self.generation is not None and self.generation!=generation:raise ValueError('nonce generation changed')
        if self.current_generation is not None and self.current_generation()!=generation:raise ValueError('stale generation')
        self.generation=generation
        if batch is not self.batch:
            self.batch=None;self.prepared=None;started=time.monotonic()
            prepared=self.plan.prepare(self.dispatch.token,batch,self.bound,self.dispatch.capacity)
            self.prepare_seconds+=time.monotonic()-started
            self.batch=batch;self.prepared=prepared;self.preparations+=1
        started=time.monotonic()
        try:result=self.dispatch.run(self.prepared,generation,capacity=capacity,current=self.current_generation)
        finally:self.scan_seconds+=time.monotonic()-started
        self.dispatches+=1;return result


def new_fast_search(context,device,current,*,start=0,on_close=None):
    from pool.search import NonceSearch,require_current
    require_current(context.job,current)
    plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return FastCandidateBackend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
