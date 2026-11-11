"""v070 CTA-shared B canonical traversal and resident-geometry dispatch, offline only. ISC."""
import ctypes as C
from dataclasses import dataclass
from pool.search import NonceSearch,require_current,Hit
from tools.fast_plan import FastPlan,FastBatch,Queries
from tools.check_tile_scan_gpu import TileQuery
from tools.lean_scan import validate_uniform
from tools.four_tile_scan import PackedFourDispatch,FourSearch
from tools.resident_scan import ResidentBackend
from tools.hoisted_a_scan import PointerBackend
from tools.job_geometry import GeometryTables

def require_cta_plan(plan):
    if type(plan)is not FastPlan or len(plan.rows)%4 or (len(plan.rows)>32 and len(plan.rows)%32):
        raise ValueError('validated multiple-of-four up to 32, otherwise multiple-of-32 row-axis count required for CTA-shared B traversal')


def cta_canonical_tile(plan,ordinal):
    require_cta_plan(plan)
    if type(ordinal)is not int or not 0<=ordinal<plan.count:raise ValueError('CTA-shared B ordinal outside plan')
    members=min(32,len(plan.rows));group,member=divmod(ordinal,members);row_group,col=divmod(group,len(plan.cols))
    return (row_group*members+member)*len(plan.cols)+col


def cta_traversal_ordinal(plan,tile):
    require_cta_plan(plan)
    if type(tile)is not int or not 0<=tile<plan.count:raise ValueError('canonical tile outside plan')
    row,col=divmod(tile,len(plan.cols))
    members=min(32,len(plan.rows))
    return (row//members)*(members*len(plan.cols))+members*col+(row%members)


def cta_coverage_interval(plan,first,stop):
    """An aligned sequence of whole row CTA row groups covers this exact canonical interval."""
    require_cta_plan(plan);period=min(32,len(plan.rows))*len(plan.cols)
    if (any(type(v)is not int for v in(first,stop))or not 0<=first<stop<=plan.count
            or first%period or stop%period):raise ValueError('whole aligned row-group interval required')
    return first,stop


class CtaBQueries(Queries):
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i]for i in range(*index.indices(len(self))))
        if type(index)is not int:raise TypeError('integer CTA-shared B query index required')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        return TileQuery(*self.batch.plan.indices(cta_canonical_tile(self.batch.plan,self.batch.start+index)))


@dataclass(frozen=True)
class CtaBPrepared:
    owner:object
    queries:CtaBQueries
    bound:int
    def __post_init__(self):
        if type(self.queries)is not CtaBQueries or type(self.queries.batch)is not FastBatch:
            raise ValueError('validated immutable CTA-shared B batch required')
        require_cta_plan(self.queries.batch.plan);validate_uniform(len(self.queries),self.bound,0,0)


class CtaBDispatch(PackedFourDispatch):
    kernel_entry=b'cta_b8_scan'
    shared=True
    def __init__(self,device,tables,cache,plan,bound):
        require_cta_plan(plan)
        super().__init__(device,tables,cache,plan,bound)

    def prepare_window(self,batch):
        if type(batch)is not FastBatch or batch.plan is not self.plan:raise ValueError('foreign CTA-shared B batch')
        return CtaBPrepared(self.token,CtaBQueries(batch),self.bound)

    def validate_window(self,batch,prepared,generation,capacity,audit):
        if (type(batch)is not FastBatch or batch.plan is not self.plan or type(prepared)is not CtaBPrepared
                or prepared.owner is not self.token or prepared.queries.batch is not batch
                or prepared.bound!=self.bound):raise ValueError('foreign CTA-shared B batch, preparation or target')
        validate_uniform(len(prepared.queries),self.bound,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('CTA-shared B queue/audit exceeds limits')

    def grid(self,count,first):
        members=min(32,len(self.plan.rows))
        return (count+first%members+members-1)//members

    scan_window=PackedFourDispatch.scan_window

class CtaBSerialDispatch(CtaBDispatch):kernel_entry=b'cta_b16_scan'
class CtaBBackend(ResidentBackend):dispatch_type=CtaBDispatch
class CtaBSerialBackend(ResidentBackend):dispatch_type=CtaBSerialDispatch

class CtaBSearch(NonceSearch):
    """Cursor is an CTA-shared B traversal ordinal; every returned Hit uses canonical ID."""
    def advance(self,tiles):
        hit,cursor=super().advance(tiles)
        if hit is not None:self.hit=Hit(hit.generation,cta_canonical_tile(self.plan,hit.tile),hit.digest)
        return self.hit,cursor


BACKENDS={'pointer-v068':PointerBackend,'cta8-v070':CtaBBackend,'cta16-v070':CtaBSerialBackend}

def new_cta_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='cta8-v070'):
    backend_type=BACKENDS[mode]
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident job maps required for packed geometry')
    plan=geometry.plan;require_cta_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):
            b_owner.validate_context(context,current)
            return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        return backend_type(profile,actual,plan=plan,bound=bound,current_generation=generation,
            on_close=on_close,tables_factory=tables_factory)
    return (FourSearch if mode=='pointer-v068'else CtaBSearch)(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
