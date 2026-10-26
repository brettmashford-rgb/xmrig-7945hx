"""Select packed/padded four-row B kernels within the validated lean lifecycle. ISC."""
import ctypes as C
from pool.search import NonceSearch,require_current
from tools.fast_plan import FastPlan
from tools.lean_scan import LeanDispatch
from tools.resident_scan import ResidentBackend


class BQuadDispatch(LeanDispatch):
    kernel_entry=b'b_quad_packed_scan'
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        try:
            self.device.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                C.byref(self.function),self.device.module,self.kernel_entry)
        except BaseException:self.close();raise


class BQuadPaddedDispatch(BQuadDispatch):kernel_entry=b'b_quad_padded_scan'
class BQuadBackend(ResidentBackend):dispatch_type=BQuadDispatch
class BQuadPaddedBackend(ResidentBackend):dispatch_type=BQuadPaddedDispatch


def new_b_quad_search(context,device,current,*,padded=False,start=0,on_close=None):
    if type(padded)is not bool:raise ValueError('boolean B layout selector required')
    require_current(context.job,current);plan=FastPlan.from_job(context.job)
    def generation():require_current(context.job,current);return context.job.generation
    def factory(profile,device,*,bound):
        backend=BQuadPaddedBackend if padded else BQuadBackend
        return backend(profile,device,plan=plan,bound=bound,current_generation=generation,on_close=on_close)
    return NonceSearch(context,device,current,start=start,backend_factory=factory,plan_factory=lambda job:plan)


def kernel_resources(dispatch):
    """Driver JIT resource facts; queried outside primary benchmark timings."""
    result={}
    for label,attribute in (('registers_per_thread',4),('static_shared_bytes',1),('local_bytes_per_thread',3)):
        value=C.c_int()
        dispatch.device.api('cuFuncGetAttribute',[C.POINTER(C.c_int),C.c_int,C.c_void_p],
            C.byref(value),attribute,dispatch.function)
        if value.value<0:raise RuntimeError('invalid kernel resource attribute')
        result[label]=value.value
    return result
