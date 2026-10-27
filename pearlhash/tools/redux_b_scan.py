"""Offline native warp XOR candidate; unchanged v060 paired traversal and lifecycle. ISC."""
from pool.search import require_current
from tools.fast_plan import FastPlan
from tools.shared_b_scan import SharedBDispatch,RowPairSearch,require_pair_plan
from tools.resident_scan import ResidentBackend

class ReduxBDispatch(SharedBDispatch):kernel_entry=b'shared_b_redux_scan'
class ReduxBBackend(ResidentBackend):dispatch_type=ReduxBDispatch

def new_redux_b_search(context,device,current,*,start=0,on_close=None):
    require_current(context.job,current);plan=FastPlan.from_job(context.job);require_pair_plan(plan)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,actual,*,bound):
        return ReduxBBackend(profile,actual,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return RowPairSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
