"""Compact-share bindings and correlated, generation-gated sends. No network/GPU. ISC."""
from dataclasses import replace
import unittest
import threading

from pool.job import _HEADER_MASK,_SCRAMBLE_KEY
from pool.search import StaleWork,prepare_base,prepare_nonce,search_nonce
from pool.session import MiningProfile,PoolSession
from pool.submission import prepare_share,SubmissionGate
from reference.patterns import PeriodicPattern
from tools.offline_nonce_search import make_job
from tools.pool_probe import decode


def fixture():
    p=PeriodicPattern.from_list([0,1,8,9,64,65,72,73])
    session=PoolSession(MiningProfile(160,192,4096,128,p,p),cert_version=3)
    header=make_job(bytes(32),3).header
    payload=bytes(v^_HEADER_MASK[i]^_SCRAMBLE_KEY[i%32]for i,v in enumerate(header))+bytes(124)
    message={'id':-1,'status':1,'result':['notify',payload.hex(),(1<<236).to_bytes(32,'little').hex(),bytes(8).hex(),'3']}
    session.consume({'id':0,'status':1,'result':True})
    session.consume({'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]})
    return session,session.consume(message),message


class Socket:
    def __init__(self,*,timeout=1,fail=False):self.packets=[];self.timeout=timeout;self.fail=fail
    def gettimeout(self):return self.timeout
    def sendall(self,data):
        self.packets.append(data)
        if self.fail:raise OSError('controlled partial write failure')


class SubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_session,job,_=fixture()
        base=prepare_base(job,cls.source_session.is_current)
        cls.context=prepare_nonce(job,base,b'TESTWORK',bytes(8),cls.source_session.is_current)
        cls.hit,_=search_nonce(cls.context,None,cls.source_session.is_current,stop=64)
        if cls.hit is None:raise RuntimeError('synthetic CPU emulation fixture found no hit')
        cls.prepared=prepare_share(cls.context,cls.hit,cls.source_session.is_current)

    def setUp(self):
        self.session,self.job,self.message=fixture()
        self.share=replace(self.prepared,job=self.job)
        self.socket=Socket();self.gate=SubmissionGate(self.session);self.gate.attach(self.socket)

    def test_compact_payload_matches_explicit_candidate_bindings(self):
        request_id=self.gate.send(self.share)
        request=decode(self.socket.packets[0]);params=request['params'][0]
        self.assertEqual((request_id,request['id'],request['method']),(1,1,'submit'))
        self.assertEqual(params,{'a_rows':list(self.share.rows),'b_cols':list(self.share.cols),
            'k':4096,'m':160,'n':192,'rank':128,'tile_h':8,'tile_w':8,'sb':1,'sb_p':[],
            'tail_mode':1,'worker_nonce':b'TESTWORK'.hex(),'miner_nonce':bytes(8).hex(),'nonce':bytes(8).hex()})
        params['a_rows'][0]=999
        self.assertEqual(self.share.parameters()['a_rows'],list(self.share.rows))
        self.assertEqual(self.gate.stats()['accepted'],0)
        with self.assertRaises(ValueError):self.gate.send(self.share)

    def test_only_exact_correlated_boolean_response_counts_once(self):
        request_id=self.gate.send(self.share)
        for bad_id in(True,str(request_id),999):
            self.assertIsNone(self.gate.response({'id':bad_id,'status':1,'result':True}))
        self.assertEqual(self.gate.stats()['pending'],1)
        result=self.gate.response({'id':request_id,'status':1,'result':True})
        self.assertEqual(result.outcome,'accepted')
        self.assertIsNone(self.gate.response({'id':request_id,'status':1,'result':True}))
        self.assertEqual((self.gate.stats()['accepted'],self.gate.stats()['duplicate_responses']),(1,1))

    def test_replacement_blocks_stale_send_but_not_old_correlated_verdict(self):
        self.session.consume(self.message)
        with self.assertRaises(StaleWork):self.gate.send(self.share)
        self.assertEqual(self.socket.packets,[])
        current=replace(self.share,job=self.session.snapshot())
        request_id=self.gate.send(current)
        self.session.consume(self.message)
        self.assertEqual(self.gate.response({'id':request_id,'status':1,'result':True}).outcome,'accepted')

    def test_write_error_invalidates_without_retry_or_acceptance(self):
        failing=Socket(fail=True);gate=SubmissionGate(self.session);gate.attach(failing)
        with self.assertRaises(ConnectionError):gate.send(self.share)
        self.assertEqual(len(failing.packets),1)
        self.assertEqual((gate.stats()['attempted'],gate.stats()['sent'],gate.stats()['send_error']),(1,0,1))
        self.assertEqual(gate.stats()['accepted'],0);self.assertTrue(self.session.closed)
        with self.assertRaises(StaleWork):gate.send(self.share)
        with self.assertRaises(ValueError):gate.attach(Socket())

    def test_reject_malformed_and_disconnect_verdicts_are_distinct(self):
        request_id=self.gate.send(self.share)
        self.assertEqual(self.gate.response({'id':request_id,'status':1,'result':False}).outcome,'rejected')
        # Isolate the malformed-response lifecycle in a fresh session.
        session,job,_=fixture();gate=SubmissionGate(session);gate.attach(Socket())
        request_id=gate.send(replace(self.prepared,job=job))
        with self.assertRaises(ConnectionError):gate.response({'id':request_id,'status':True,'result':True})
        self.assertEqual(gate.stats()['protocol_error'],1);self.assertEqual(gate.stats()['accepted'],0)
        self.assertTrue(session.closed)
        session,job,_=fixture();gate=SubmissionGate(session);gate.attach(Socket())
        gate.send(replace(self.prepared,job=job));gate.detach()
        self.assertEqual(gate.stats()['disconnected'],1);self.assertEqual(gate.stats()['accepted'],0)

    def test_pending_timeout_and_id_limits(self):
        session,job,_=fixture()
        for timeout in(None,0,11):
            with self.assertRaises(ValueError):SubmissionGate(session).attach(Socket(timeout=timeout))
        gate=SubmissionGate(session,max_pending=1);gate.attach(Socket());share=replace(self.prepared,job=job)
        gate.send(share)
        with self.assertRaises(RuntimeError):gate.send(share)
        self.gate.next_id=0x80000000
        with self.assertRaises(ConnectionError):self.gate.send(self.share)
        self.assertEqual(self.socket.packets,[])

    def test_job_replacement_cannot_interleave_the_locked_socket_write(self):
        entered=threading.Event();release=threading.Event();attempted=threading.Event();replaced=threading.Event()
        sent=[];errors=[]
        class Blocking(Socket):
            def sendall(stream,data):
                entered.set()
                if not release.wait(3):raise OSError('controlled write timeout')
                stream.packets.append(data)
        gate=SubmissionGate(self.session);stream=Blocking();gate.attach(stream)
        def send():
            try:sent.append(gate.send(self.share))
            except Exception as error:errors.append(error)
        def update():
            attempted.set()
            try:self.session.consume(self.message);replaced.set()
            except Exception as error:errors.append(error)
        sender=threading.Thread(target=send);updater=threading.Thread(target=update)
        try:
            sender.start();self.assertTrue(entered.wait(3));updater.start()
            self.assertTrue(attempted.wait(3));self.assertFalse(replaced.is_set())
        finally:
            release.set();sender.join(3)
            if updater.ident is not None:updater.join(3)
        self.assertFalse(sender.is_alive());self.assertFalse(updater.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(sent,[1]);self.assertTrue(replaced.is_set())
        self.assertEqual(len(stream.packets),1);self.assertFalse(self.session.is_current(self.share.job))

    def test_builder_rechecks_cpu_math_and_immutable_profile(self):
        with self.assertRaisesRegex(ValueError,'candidate digest'):
            prepare_share(self.context,replace(self.hit,digest=bytes(32)),self.source_session.is_current)
        with self.assertRaises(ValueError):
            prepare_share(replace(self.context,profile=replace(self.context.profile,fill=-64)),self.hit,self.source_session.is_current)


if __name__=='__main__':unittest.main()
