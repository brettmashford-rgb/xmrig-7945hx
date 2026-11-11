"""v071 independent transcript-fold experiment with unchanged job geometry/B ownership. ISC."""
from pool.search import require_current
from tools.job_geometry import GeometryTables
from tools.four_tile_scan import PackedFourBackend,PackedFourDispatch,FourSearch,require_four_plan


class PartitionDispatch(PackedFourDispatch):
    kernel_entry=b'partition_pointer_scan'
class NativeDispatch(PackedFourDispatch):
    kernel_entry=b'native_pointer_scan'
class PartitionBackend(PackedFourBackend):
    dispatch_type=PartitionDispatch
class NativeBackend(PackedFourBackend):
    dispatch_type=NativeDispatch
from tools.hoisted_a_scan import PointerBackend
BACKENDS={'pointer-v068':PointerBackend,'partition-v071':PartitionBackend,'native-v071':NativeBackend}

def new_partition_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='partition-v071'):
    backend_type=BACKENDS[mode]
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident job maps required for packed geometry')
    plan=geometry.plan;require_four_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):
            b_owner.validate_context(context,current)
            return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        return backend_type(profile,actual,plan=plan,bound=bound,current_generation=generation,
            on_close=on_close,tables_factory=tables_factory)
    return FourSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
