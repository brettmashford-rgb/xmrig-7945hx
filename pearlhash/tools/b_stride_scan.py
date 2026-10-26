"""Compare validated quad5 with strides six/seven; unchanged lean lifecycle. ISC."""
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.b_quad_scan import BQuadDispatch,BQuadPaddedBackend
from tools.resident_scan import ResidentBackend


class BStride6Dispatch(BQuadDispatch):kernel_entry=b'b_quad_stride6_scan'
class BStride7Dispatch(BQuadDispatch):kernel_entry=b'b_quad_stride7_scan'
class BStride6Backend(ResidentBackend):dispatch_type=BStride6Dispatch
class BStride7Backend(ResidentBackend):dispatch_type=BStride7Dispatch


def new_b_stride_search(context,device,current,*,stride=5,start=0,on_close=None):
    if type(stride)is not int or stride not in(5,6,7):raise ValueError('B stride must be integer five, six or seven')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    backend={5:BQuadPaddedBackend,6:BStride6Backend,7:BStride7Backend}[stride]
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)
