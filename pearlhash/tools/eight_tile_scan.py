"""v069 eight-tile canonical traversal and resident-geometry dispatch, offline only. ISC."""
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

def require_eight_plan(plan):
    if type(plan)is not FastPlan or len(plan.rows)%8:
        raise ValueError('validated multiple-of-eight row-axis count required for eight-tile traversal')


def eight_canonical_tile(plan,ordinal):
    require_eight_plan(plan)
    if type(ordinal)is not int or not 0<=ordinal<plan.count:raise ValueError('eight-tile ordinal outside plan')
    octet,member=divmod(ordinal,8);row_group,col=divmod(octet,len(plan.cols))
    return (row_group*8+member)*len(plan.cols)+col


def eight_traversal_ordinal(plan,tile):
    require_eight_plan(plan)
    if type(tile)is not int or not 0<=tile<plan.count:raise ValueError('canonical tile outside plan')
    row,col=divmod(tile,len(plan.cols))
    return (row//8)*(8*len(plan.cols))+8*col+(row%8)


def eight_coverage_interval(plan,first,stop):
    """An aligned sequence of whole row octets covers this exact canonical interval."""
    require_eight_plan(plan);period=8*len(plan.cols)
    if (any(type(v)is not int for v in(first,stop))or not 0<=first<stop<=plan.count
            or first%period or stop%period):raise ValueError('whole aligned row-octet interval required')
    return first,stop


class EightQueries(Queries):
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i]for i in range(*index.indices(len(self))))
        if type(index)is not int:raise TypeError('integer eight-tile query index required')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        return TileQuery(*self.batch.plan.indices(eight_canonical_tile(self.batch.plan,self.batch.start+index)))


@dataclass(frozen=True)
class EightPrepared:
    owner:object
    queries:EightQueries
    bound:int
    def __post_init__(self):
        if type(self.queries)is not EightQueries or type(self.queries.batch)is not FastBatch:
            raise ValueError('validated immutable eight-tile batch required')
        require_eight_plan(self.queries.batch.plan);validate_uniform(len(self.queries),self.bound,0,0)


class EightDispatch(PackedFourDispatch):
    kernel_entry=b'eight_tile_packed_scan'
    shared=True
    def __init__(self,device,tables,cache,plan,bound):
        require_eight_plan(plan)
        super().__init__(device,tables,cache,plan,bound)

    def prepare_window(self,batch):
        if type(batch)is not FastBatch or batch.plan is not self.plan:raise ValueError('foreign eight-tile batch')
        return EightPrepared(self.token,EightQueries(batch),self.bound)

    def validate_window(self,batch,prepared,generation,capacity,audit):
        if (type(batch)is not FastBatch or batch.plan is not self.plan or type(prepared)is not EightPrepared
                or prepared.owner is not self.token or prepared.queries.batch is not batch
                or prepared.bound!=self.bound):raise ValueError('foreign eight-tile batch, preparation or target')
        validate_uniform(len(prepared.queries),self.bound,capacity,generation)
        if capacity>self.capacity or type(audit)is not bool:raise ValueError('eight-tile queue/audit exceeds limits')

    def grid(self,count,first):
        return (count+(first&7)+63)//64

    scan_window=PackedFourDispatch.scan_window

class EightSerialDispatch(EightDispatch):kernel_entry=b'eight_tile_serial_scan'
class EightBackend(ResidentBackend):dispatch_type=EightDispatch
class EightSerialBackend(ResidentBackend):dispatch_type=EightSerialDispatch

class EightSearch(NonceSearch):
    """Cursor is an eight-tile traversal ordinal; every returned Hit uses canonical ID."""
    def advance(self,tiles):
        hit,cursor=super().advance(tiles)
        if hit is not None:self.hit=Hit(hit.generation,eight_canonical_tile(self.plan,hit.tile),hit.digest)
        return self.hit,cursor


BACKENDS={'pointer-v068':PointerBackend,'eight-v069':EightBackend,'eight-serial-v069':EightSerialBackend}

def new_eight_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='eight-v069'):
    backend_type=BACKENDS[mode]
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident job maps required for packed geometry')
    plan=geometry.plan;require_eight_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):
            b_owner.validate_context(context,current)
            return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        return backend_type(profile,actual,plan=plan,bound=bound,current_generation=generation,
            on_close=on_close,tables_factory=tables_factory)
    return (FourSearch if mode=='pointer-v068'else EightSearch)(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
