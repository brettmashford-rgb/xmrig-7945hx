"""Bounded periodic tile planning and generation-gated dispatch. ISC.

No network, seed derivation, target scaling or full-matrix allocation. A backend
returns an object with overflow and require_complete() (local tile -> digest).
This is range scheduling, not a live pool job/cancellation implementation.
"""
from dataclasses import dataclass
from reference.patterns import PeriodicPattern


class PatternDomain:
    """Random-access valid pattern offsets without enumerating matrix rows."""
    def __init__(self,dimension,pattern):
        if (type(dimension)is not int or not 1<=dimension<=0xffffffff
            or not isinstance(pattern,PeriodicPattern)or not 1<=pattern.size<=32):
            raise ValueError('invalid dimension or bounded scan pattern')
        self.dimension=dimension;self.pattern=pattern;self.relative=tuple(pattern.to_list())
        period=count=1;self.digits=[]
        for i in range(0,6,2):
            factor,length=pattern.encoded[i]+1,pattern.encoded[i+1]+1
            self.digits.append((count,period,factor));count*=factor;period*=factor*length
        self.residues=count;self.period=period
        limit=dimension-1-self.relative[-1]
        if limit<0:self.count=0;return
        periods,remainder=divmod(limit,period)
        lo,hi=0,count
        while lo<hi:
            mid=(lo+hi)//2
            if self._residue(mid)<=remainder:lo=mid+1
            else:hi=mid
        self.count=periods*count+lo

    def _residue(self,index):
        return sum(((index//count)%factor)*period for count,period,factor in self.digits)

    def offset(self,index):
        if type(index)is not int or not 0<=index<self.count:raise ValueError('tile offset index out of range')
        period,residue=divmod(index,self.residues)
        return period*self.period+self._residue(residue)

    def indices(self,index):
        offset=self.offset(index);return tuple(offset+v for v in self.relative)


@dataclass(frozen=True)
class RangeBatch:
    start:int
    stop:int
    rows:tuple
    cols:tuple
    maps:tuple


class RangePlan:
    def __init__(self,a,b,*,batch_queries=64):
        if not isinstance(a,PatternDomain)or not isinstance(b,PatternDomain):raise ValueError('expected pattern domains')
        if type(batch_queries)is not int or not 1<=batch_queries<=64:raise ValueError('invalid batch query cap')
        self.a=a;self.b=b;self.count=a.count*b.count;self.batch_queries=batch_queries

    def indices(self,tile):
        if type(tile)is not int or not 0<=tile<self.count:raise ValueError('tile ID out of range')
        row,col=divmod(tile,self.b.count);return self.a.indices(row),self.b.indices(col)

    def batches(self,start,stop):
        if any(type(v)is not int for v in (start,stop))or not 0<=start<=stop<=self.count:
            raise ValueError('invalid tile interval')
        position=start
        while position<stop:
            first=position;rows={};cols={};maps=[]
            while position<stop and len(maps)<self.batch_queries:
                ra,cb=self.indices(position)
                if len(set(rows).union(ra))>32 or len(set(cols).union(cb))>32:break
                for row in ra:
                    if row not in rows:rows[row]=len(rows)
                for col in cb:
                    if col not in cols:cols[col]=len(cols)
                maps.append((tuple(rows[row]for row in ra),tuple(cols[col]for col in cb)))
                position+=1
            if position==first:raise ValueError('tile exceeds bounded row/column pools')
            yield RangeBatch(first,position,tuple(rows),tuple(cols),tuple(maps))


@dataclass
class RangeCursor:
    generation:int
    next_tile:int
    stop:int
    status:str='ready'
    batches_done:int=0
    retries:int=0


def run_range(plan,cursor,backend,current_generation,on_candidates,*,initial_capacity=1):
    """Dispatch bounded batches and commit a cursor only after complete results.

    Generation is checked before launches/retries and before candidate delivery.
    Cancellation discards the unfinished batch and leaves its start resumable.
    The synchronous callback must be idempotent if it raises after side effects;
    the cursor does not advance when backend validation/callback delivery fails.
    No live pool listener or externally atomic share-submission gate is implied.
    """
    if (type(cursor.generation)is not int or not 0<=cursor.generation<=0xffffffffffffffff
        or any(type(v)is not int for v in (cursor.next_tile,cursor.stop,initial_capacity))
        or not 0<=cursor.next_tile<=cursor.stop<=plan.count or not 0<=initial_capacity<=64):
        raise ValueError('invalid range cursor or capacity')
    def cancelled():
        generation=current_generation()
        if type(generation)is not int or not 0<=generation<=0xffffffffffffffff:
            raise ValueError('current generation must be u64')
        if generation!=cursor.generation:
            cursor.status='cancelled';return True
        return False
    for batch in plan.batches(cursor.next_tile,cursor.stop):
        if cancelled():return cursor
        result=backend(batch,initial_capacity,cursor.generation)
        if cancelled():return cursor
        if result.overflow:
            cursor.retries+=1
            result=backend(batch,len(batch.maps),cursor.generation)
            if cancelled():return cursor
        records=result.require_complete()
        if result.total!=len(records)or any(type(i)is not int or not 0<=i<len(batch.maps)
            or type(d)is not bytes or len(d)!=32 for i,d in records.items()):
            raise ValueError('invalid complete backend result')
        if cancelled():return cursor
        on_candidates(tuple((batch.start+i,d,cursor.generation)for i,d in sorted(records.items())))
        cursor.next_tile=batch.stop;cursor.batches_done+=1;cursor.status='running'
    cursor.status='complete';return cursor
