"""Fresh job B commitment on a temporary GPU context; independent CPU opening check. ISC."""
from pool.search import Base,require_current
from tools.gpu_constant_merkle import ConstantMerkleGpu


def prepare_gpu_base(job,current,module):
    require_current(job,current)
    device=ConstantMerkleGpu()
    try:
        device.start(module)
        p=job.profile
        opening=device.opening(job.job_key,64,p.n*p.k//1024,[0],p.k,
                               current=lambda:require_current(job,current))
        require_current(job,current)
        return Base(job.job_key,p.n,p.k,opening)
    finally:device.close()
