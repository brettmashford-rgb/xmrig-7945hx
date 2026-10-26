"""Butterfly byte transpose for B fragments; established lean lifecycle. ISC."""
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.b_quad_scan import BQuadDispatch,BQuadPaddedBackend
from tools.resident_scan import ResidentBackend


class BTransposeDispatch(BQuadDispatch):kernel_entry=b'b_quad_transpose_scan'
class BTransposeBackend(ResidentBackend):dispatch_type=BTransposeDispatch


def new_transpose_search(context,device,current,*,transpose=True,start=0,on_close=None):
    if type(transpose)is not bool:raise ValueError('boolean B transpose selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    backend=BTransposeBackend if transpose else BQuadPaddedBackend
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
