"""CPU-checked compact shares and a same-connection submission gate. ISC.

No connection creation/reconnect. An eventual receiver adapter owns the socket,
feeds replies here and detaches on connection end. This component is not yet
wired into the live runner. Worker nonce remains an explicit caller input;
assigned-extranonce mapping and actual custom pool acceptance are unverified.
"""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib

from pool.search import build_proof, plan_for, require_current
from pool.session import PoolSession
from tools.pool_probe import encode


@dataclass(frozen=True)
class PreparedShare:
    job: object
    tile: int
    rows: tuple
    cols: tuple
    worker: bytes
    miner: bytes
    digest: bytes
    proof: bytes

    def parameters(self):
        p=self.job.profile
        return {'a_rows':list(self.rows),'b_cols':list(self.cols),'k':p.k,'m':p.m,'n':p.n,
                'rank':p.rank,'tile_h':p.rows.size,'tile_w':p.cols.size,'sb':1,'sb_p':[],
                'tail_mode':1,'worker_nonce':self.worker.hex(),
                'miner_nonce':self.miner.hex(),'nonce':self.miner.hex()}


def prepare_share(context, hit, current):
    """Recompute candidate math, roots/seeds/openings before forming compact IO."""
    p=context.job.profile;c=context.profile
    if (c.m,c.n,c.k,c.rank,c.fill)!=(p.m,p.n,p.k,p.rank,64):
        raise ValueError('compact share requires the explicit dense constant64 profile')
    proof,_=build_proof(context,hit,current)
    rows,cols=plan_for(context.job).indices(hit.tile)
    require_current(context.job,current)
    return PreparedShare(context.job,hit.tile,tuple(rows),tuple(cols),context.worker,
                         context.miner,hit.digest,proof)


@dataclass(frozen=True)
class SubmissionResult:
    request_id: int
    generation: int
    outcome: str
    status: object=None


class SubmissionGate:
    """One attached connection; atomic current-job check/write, bounded ledger.

    Expensive proof construction happens before this gate. Holding the session
    lock serializes a bounded socket send with incoming job replacement. The
    socket owner must set a finite write timeout. A write error invalidates the
    connection; no ambiguous request is retried. Future status request IDs must
    use this same connection's allocator, never an independent counter.
    """
    HISTORY_CAP=4096
    def __init__(self,session,*,max_pending=4):
        if not isinstance(session,PoolSession) or type(max_pending)is not int or not 1<=max_pending<=16:
            raise ValueError('configured session and bounded pending limit required')
        self.session=session;self.max_pending=max_pending
        self.stream=None;self.attached_once=False;self.next_id=1
        self.pending={};self.history=OrderedDict();self.recent=OrderedDict()
        self.attempted=self.sent=self.duplicates=0
        self.counts={name:0 for name in('accepted','rejected','disconnected','send_error','protocol_error')}

    def attach(self,stream):
        with self.session.lock:
            if self.attached_once or self.session.closed or not callable(getattr(stream,'sendall',None))or not callable(getattr(stream,'gettimeout',None)):
                raise ValueError('one live socket attachment per gate required')
            timeout=stream.gettimeout()
            if timeout is None or not 0<timeout<=10:
                raise ValueError('attached socket requires a finite timeout up to ten seconds')
            self.stream=stream;self.attached_once=True

    def _record(self,request_id,generation,outcome,status=None):
        result=SubmissionResult(request_id,generation,outcome,status)
        self.history[request_id]=result;self.counts[outcome]+=1
        while len(self.history)>self.HISTORY_CAP:self.history.popitem(last=False)
        return result

    def _disconnect(self):
        self.stream=None
        for request_id,generation in tuple(self.pending.items()):
            self._record(request_id,generation,'disconnected')
        self.pending.clear();self.session.close()

    def detach(self):
        with self.session.lock:self._disconnect()

    def send(self,share):
        # PreparedShare is an internal trusted-runtime object, not an arbitrary
        # Python-code authorization boundary. Validate immutable IO bindings.
        if not isinstance(share,PreparedShare):raise ValueError('CPU-prepared share required')
        p=share.job.profile
        rows,cols=plan_for(share.job).indices(share.tile)
        if (share.rows!=tuple(rows) or share.cols!=tuple(cols)
                or any(type(v)is not bytes or len(v)!=8 for v in(share.worker,share.miner))
                or type(share.digest)is not bytes or len(share.digest)!=32
                or int.from_bytes(share.digest,'little')>share.job.share_bound
                or type(share.proof)is not bytes or not 1<=len(share.proof)<=8*1024**2
                or share.job.cert_version!=3 or p.rank!=128):
            raise ValueError('compact share binding differs')
        fingerprint=hashlib.sha256(share.job.generation.to_bytes(8,'little')+
            share.tile.to_bytes(8,'little')+share.worker+share.miner+share.digest).digest()
        with self.session.lock:
            require_current(share.job,self.session.is_current)
            if self.stream is None:raise ConnectionError('no attached submission connection')
            if len(self.pending)>=self.max_pending:raise RuntimeError('pending share limit reached')
            if fingerprint in self.recent:raise ValueError('recent duplicate share blocked')
            if self.next_id>0x7fffffff:
                self._disconnect();raise ConnectionError('request ID space exhausted')
            request_id=self.next_id;self.next_id+=1
            packet=encode({'id':request_id,'method':'submit','params':[share.parameters()]})
            self.pending[request_id]=share.job.generation;self.recent[fingerprint]=None
            while len(self.recent)>self.HISTORY_CAP:self.recent.popitem(last=False)
            self.attempted+=1
            try:self.stream.sendall(packet)
            except OSError:
                generation=self.pending.pop(request_id)
                self._record(request_id,generation,'send_error');self._disconnect()
                raise ConnectionError('share write failed; connection invalidated; no automatic retry')from None
            self.sent+=1
            return request_id

    def response(self,message):
        with self.session.lock:
            if not isinstance(message,dict)or type(message.get('id'))is not int:return None
            request_id=message['id']
            if request_id in self.history:
                self.duplicates+=1;return None
            if request_id not in self.pending:return None
            generation=self.pending.pop(request_id)
            status=message.get('status');value=message.get('result')
            if type(status)is not int or type(value)is not bool or message.get('error')is not None:
                self._record(request_id,generation,'protocol_error');self._disconnect()
                raise ConnectionError('malformed correlated share response; connection invalidated')
            outcome='accepted'if status==1 and value is True else'rejected'
            return self._record(request_id,generation,outcome,status)

    def stats(self):
        with self.session.lock:
            return dict(self.counts,attempted=self.attempted,sent=self.sent,pending=len(self.pending),
                        duplicate_responses=self.duplicates,attached=self.stream is not None)
