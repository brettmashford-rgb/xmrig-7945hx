"""v072 combined scanner; actual winning v070/v071 entries retained as controls. ISC."""
from pool.search import require_current
from tools.job_geometry import GeometryTables
from tools.cta_b_scan import CtaBDispatch,CtaBBackend,CtaBSearch,require_cta_plan
from tools.four_tile_scan import FourSearch
from tools.partition_scan import PartitionBackend

class CombinedDispatch(CtaBDispatch):kernel_entry=b'combined_scan'
class CombinedBackend(CtaBBackend):dispatch_type=CombinedDispatch
BACKENDS={'cta8-v070':CtaBBackend,'partition-v071':PartitionBackend,'combined-v072':CombinedBackend}

def new_combined_search(context,device,current,b_owner,geometry,*,start=0,on_close=None,mode='combined-v072'):
    backend_type=BACKENDS[mode]
    geometry.validate(context,device,current);b_owner.validate_context(context,current)
    if not geometry.maps:raise ValueError('resident job maps required for combined search')
    plan=geometry.plan;require_cta_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        def tables_factory(actual,profile):
            b_owner.validate_context(context,current)
            return GeometryTables(actual,profile,context=context,current=current,b_owner=b_owner,geometry=geometry)
        return backend_type(profile,actual,plan=plan,bound=bound,current_generation=generation,
            on_close=on_close,tables_factory=tables_factory)
    search_type=FourSearch if mode=='partition-v071'else CtaBSearch
    return search_type(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
