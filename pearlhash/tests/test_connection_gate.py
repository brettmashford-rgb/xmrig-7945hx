"""Same-stream submit/status correlation and teardown; no external connections. ISC."""
from dataclasses import replace
import unittest

from pool.receiver import PoolReceiver
from pool.submission import SubmissionGate
from test_submission import fixture,Socket
from tools.pool_probe import decode,encode


class ConnectionTests(unittest.TestCase):
    def test_status_ids_share_allocator_but_never_credit_shares(self):
        state,job,_=fixture();gate=SubmissionGate(state);stream=Socket();gate.attach(stream)
        first=gate.report_info(123.5,'PearlHash independent GPU')
        self.assertEqual(decode(stream.packets[0]),{'id':1,'method':'report_info',
            'params':[{'hashrate':123.5,'name':'PearlHash independent GPU'}]})
        self.assertIsNone(gate.report_info(0,'own miner'))
        gate.response({'id':first,'status':1,'result':True})
        self.assertEqual(gate.next_id,2)
        self.assertEqual(gate.stats()['accepted'],0)
        self.assertEqual(gate.stats()['reports']['accepted'],1)
        self.assertIsNone(gate.response({'id':first,'status':1,'result':True}))
        for rate in (True,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):gate.report_info(rate,'own miner')
        gate.report_info(0,'own miner');gate.detach()
        self.assertEqual(gate.stats()['reports']['disconnected'],1)

    def test_status_write_failure_and_malformed_ack_close_session(self):
        state,_,_=fixture();gate=SubmissionGate(state);gate.attach(Socket(fail=True))
        with self.assertRaises(ConnectionError):gate.report_info(0,'own miner')
        self.assertTrue(state.closed);self.assertEqual(gate.stats()['accepted'],0)
        state,_,_=fixture();gate=SubmissionGate(state);gate.attach(Socket())
        ident=gate.report_info(0,'own miner')
        with self.assertRaises(ConnectionError):gate.response({'id':ident,'status':1,'result':1})
        self.assertTrue(state.closed)

    def test_receiver_attaches_routes_and_detaches_same_stream(self):
        state,_,notify=fixture();gate=SubmissionGate(state);verdicts=[]
        class Stream(Socket):
            def __init__(self):super().__init__();self.step=0;self.closed=False
            def __enter__(self):return self
            def __exit__(self,*args):
                self.closed=True
                # The gate must become unusable before socket close.
                self_detached=gate.stream is None
                if not self_detached:raise AssertionError('gate still attached at socket close')
            def settimeout(self,value):self.timeout=value
            def recv(self,size):
                self.step+=1
                if self.step==1:return b''.join(encode(x)for x in (
                    {'id':0,'status':1,'result':True},
                    {'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]},notify))
                if self.step==2:return encode({'id':1,'status':1,'result':True})
                return b''
        stream=Stream()
        def job_received(job):
            self.assertIs(gate.stream,stream)
            gate.report_info(0,'own miner')
        result=PoolReceiver(state,'synthetic.example',9000,'synthetic-wallet','own-worker',
            connect=lambda *a,**k:stream).run(job_received,gate=gate,on_response=verdicts.append)
        self.assertEqual(result.jobs,1);self.assertTrue(stream.closed)
        self.assertEqual([decode(p)['method']for p in stream.packets],['login','report_info'])
        self.assertEqual(verdicts,[]);self.assertEqual(gate.stats()['accepted'],0)
        self.assertEqual(gate.stats()['reports']['accepted'],1);self.assertTrue(state.closed)


if __name__=='__main__':unittest.main()
