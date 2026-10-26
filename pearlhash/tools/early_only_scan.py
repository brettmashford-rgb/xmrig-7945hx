"""Early operand preparation without grouping; established lean lifecycle. ISC."""
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.b_quad_scan import BQuadDispatch,BQuadPaddedBackend
from tools.resident_scan import ResidentBackend


class EarlyOnlyDispatch(BQuadDispatch):kernel_entry=b'b_quad_early_only_scan'
class EarlyOnlyBackend(ResidentBackend):dispatch_type=EarlyOnlyDispatch


def new_early_search(context,device,current,*,early=True,start=0,on_close=None):
    if type(early)is not bool:raise ValueError('boolean early operand selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    backend=EarlyOnlyBackend if early else BQuadPaddedBackend
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
