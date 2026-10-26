"""Verified immutable last-leaf A frontier, offline nonce preparation experiment. ISC."""
from dataclasses import dataclass,field
from pool.search import Base,Nonce,require_current
from reference.constant_merkle import constant_opening
from reference.native_hash import key_check,chunk_value,parents
from reference.plain_proof import Opening
from reference.pool_nonce import nonce_tail
from reference.seeds import dense_noise_seeds
from tools.check_range_scan_gpu import ConstantProfile

_VERIFIED=object()
_BLOCK=bytes([64])*1024


def _last_frontier(opening,key):
    """Extract the last leaf's fixed siblings from an independently verified row opening."""
    opening.verify(key)
    nodes={i:chunk_value(data,i,key)for i,data in zip(opening.leaf_indices,opening.leaves,strict=True)}
    length=opening.total_leaves;target=length-1;cursor=0;siblings=[]
    if target not in nodes:raise ValueError('frontier opening must include the last leaf')
    while length>1:
        current=dict(nodes)
        for i in sorted(nodes):
            sibling=i^1
            if sibling<length and sibling not in current:
                if cursor>=len(opening.siblings):raise ValueError('frontier opening missing sibling')
                current[sibling]=opening.siblings[cursor];cursor+=1
        sibling=target^1
        if sibling<length:siblings.append(current[sibling])
        next_level={}
        for parent in sorted({i//2 for i in nodes}):
            left=2*parent;right=left+1
            next_level[parent]=(parents([current[left],current[right]],key,root=length==2)[0]
                                if right<length else current[left])
        nodes=next_level;length=(length+1)//2;target//=2
    if cursor!=len(opening.siblings)or nodes[0]!=opening.root:raise ValueError('frontier extraction differs')
    return tuple(siblings)


@dataclass(frozen=True)
class NonceCommitmentCache:
    key:bytes=field(repr=False)
    m:int
    k:int
    baseline_root:bytes=field(repr=False)
    siblings:tuple=field(repr=False)
    _ticket:object=field(repr=False,compare=False)

    def __post_init__(self):
        key_check(self.key)
        if (type(self.m)is not int or not 1<=self.m<=8192 or type(self.k)is not int or self.k!=32768
                or type(self.baseline_root)is not bytes or len(self.baseline_root)!=32
                or type(self.siblings)is not tuple or any(type(s)is not bytes or len(s)!=32 for s in self.siblings)
                or self._ticket is not _VERIFIED):raise ValueError('verified production A frontier required')
        Opening([_BLOCK],[self.total_leaves-1],self.total_leaves,self.baseline_root,list(self.siblings),[]).verify(self.key)

    @property
    def total_leaves(self):return self.m*self.k//1024

    @classmethod
    def build(cls,job,current):
        require_current(job,current);p=job.profile
        if (type(p.m)is not int or not 1<=p.m<=8192 or p.k!=32768 or p.rank!=128):
            raise ValueError('production A frontier profile required')
        opening=constant_opening(job.job_key,64,p.m*p.k//1024,[p.m-1],p.k)
        require_current(job,current)
        siblings=_last_frontier(opening,job.job_key)
        result=cls(job.job_key,p.m,p.k,opening.root,siblings,_VERIFIED)
        require_current(job,current)
        return result

    def root(self,tail):
        if type(tail)is not bytes or len(tail)!=16:raise ValueError('exact sixteen-byte nonce tail required')
        leaf=_BLOCK[:-16]+tail;index=self.total_leaves-1;length=self.total_leaves;cursor=0
        value=chunk_value(leaf,index,self.key)
        while length>1:
            sibling=index^1
            if sibling<length:
                if cursor>=len(self.siblings):raise ValueError('frontier sibling missing')
                other=self.siblings[cursor];cursor+=1
                value=parents([other,value]if index&1 else[value,other],self.key,root=length==2)[0]
            index//=2;length=(length+1)//2
        if cursor!=len(self.siblings):raise ValueError('extra frontier siblings')
        # Independent existing sparse-opening verifier checks every resulting root.
        # This is a last-leaf membership proof, not a full row opening for PlainProof.
        Opening([leaf],[self.total_leaves-1],self.total_leaves,value,list(self.siblings),[]).verify(self.key)
        return value


def prepare_cached_nonce(job,base,worker,miner,current,cache):
    """Same Nonce contract as prepare_nonce; fresh candidate proofs remain unchanged."""
    require_current(job,current)
    if any(type(v)is not bytes or len(v)!=8 for v in(worker,miner)):
        raise ValueError('explicit eight-byte worker and miner nonces required')
    p=job.profile
    if (not isinstance(base,Base)or (base.job_key,base.n,base.k)!=(job.job_key,p.n,p.k)
            or base.opening.total_leaves!=p.n*p.k//1024 or base.opening.rows!=[0]):
        raise ValueError('base commitment belongs to a different job/profile')
    if (type(cache)is not NonceCommitmentCache or (cache.key,cache.m,cache.k)!=(job.job_key,p.m,p.k)
            or p.rank!=128):raise ValueError('A frontier belongs to a different job/profile')
    base.opening.verify(job.job_key)
    tail=nonce_tail(worker,miner);root=cache.root(tail)
    require_current(job,current)
    bs,ass=dense_noise_seeds(job.job_key,root,base.opening.root,p.m,p.n,cert_version=job.cert_version)
    profile=ConstantProfile(p.m,p.n,p.k,p.rank,64,tail,ass,bs)
    return Nonce(job,worker,miner,base,root,profile)
