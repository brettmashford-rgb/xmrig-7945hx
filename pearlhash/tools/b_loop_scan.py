"""Compare validated quad5 with grouped/early operand loops; unchanged lean lifecycle. ISC."""
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.b_quad_scan import BQuadDispatch,BQuadPaddedBackend
from tools.resident_scan import ResidentBackend


class BGroupedDispatch(BQuadDispatch):kernel_entry=b'b_quad_grouped_scan'
class BEarlyDispatch(BQuadDispatch):kernel_entry=b'b_quad_early_scan'
class BGroupedBackend(ResidentBackend):dispatch_type=BGroupedDispatch
class BEarlyBackend(ResidentBackend):dispatch_type=BEarlyDispatch


def new_b_loop_search(context,device,current,*,variant='quad5',start=0,on_close=None):
    if type(variant)is not str or variant not in('quad5','grouped','early'):raise ValueError('variant must be quad5, grouped or early')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    backend={'quad5':BQuadPaddedBackend,'grouped':BGroupedBackend,'early':BEarlyBackend}[variant]
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
