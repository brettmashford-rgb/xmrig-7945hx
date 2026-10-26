"""Retest stride-six padding on v57 transpose; established lean lifecycle. ISC."""
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.b_quad_scan import BQuadDispatch
from tools.b_transpose_scan import BTransposeBackend
from tools.resident_scan import ResidentBackend


class Transpose6Dispatch(BQuadDispatch):kernel_entry=b'b_quad_transpose6_scan'
class Transpose6Backend(ResidentBackend):dispatch_type=Transpose6Dispatch


def new_transpose6_search(context,device,current,*,padded=True,start=0,on_close=None):
    if type(padded)is not bool:raise ValueError('boolean stride-six selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    backend=Transpose6Backend if padded else BTransposeBackend
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
