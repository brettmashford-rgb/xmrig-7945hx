"""Runner orchestration with fake GPU/math and a scripted pool, never live mining. ISC."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pool.search import Hit,plan_for
from pool.submission import PreparedShare
from tools import mine_bounded as runner
from tools.pool_probe import encode,decode


class RunnerTests(unittest.TestCase):
    def test_new_candidate_proof_send_correlated_verdict_and_cleanup(self):
        self.run_attempt(False)

    def test_full_domain_rolls_to_fresh_nonce_before_next_candidate(self):
        self.run_attempt(True)

    def test_target_only_mode_does_not_prepare_or_start_gpu(self):
        class Stream:
            def __init__(self):self.packets=[];self.timeout=1;self.closed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def settimeout(self,value):self.timeout=value
            def gettimeout(self):return self.timeout
            def sendall(self,data):self.packets.append(decode(data))
            def recv(self,size):return b''.join(encode(x)for x in (
                {'id':0,'status':1,'result':True},
                {'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]},
                {'id':-1,'status':1,'result':['notify',bytes(200).hex(),
                 (1<<200).to_bytes(32,'little').hex(),bytes(8).hex(),'3']}))
        stream=Stream();actual_receiver=runner.PoolReceiver
        def receiver(*args,**kwargs):return actual_receiver(*args,**kwargs,connect=lambda *a,**k:stream)
        with tempfile.TemporaryDirectory()as folder,ExitStack()as stack:
            report=Path(folder)/'observation.json'
            stack.enter_context(patch.object(runner,'PoolReceiver',receiver))
            stack.enter_context(patch.object(runner,'saved_wallet',return_value='synthetic-wallet'))
            prepare=stack.enter_context(patch.object(runner,'prepare_base'))
            gpu=stack.enter_context(patch.object(runner,'ProductionCandidateScanner'))
            stack.enter_context(patch('sys.argv',['mine_bounded','--host','synthetic.example','--port','9000',
                '--login-file','unused','--module','unused','--report',str(report),'--seconds','3','--observe-target']))
            self.assertEqual(runner.main(),0);prepare.assert_not_called();gpu.assert_not_called()
            data=json.loads(report.read_text());self.assertEqual(data['worker']['started'],0)
            self.assertEqual(data['submitted_shares'],0);self.assertEqual(len(data['telemetry']['jobs']),1)
            self.assertEqual([p['method']for p in stream.packets],['login'])
        self.assertTrue(stream.closed)

    def run_attempt(self,rollover):
        events=[];ready=threading.Event()
        class Stream:
            def __init__(self):self.packets=[];self.step=0;self.timeout=1;self.closed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def settimeout(self,value):self.timeout=value
            def gettimeout(self):return self.timeout
            def sendall(self,data):
                request=decode(data);self.packets.append(request)
                if request['method']=='submit':ready.set()
            def recv(self,size):
                self.step+=1
                if self.step==1:return b''.join(encode(x)for x in (
                    {'id':0,'status':1,'result':True},
                    {'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]},
                    {'id':-1,'status':1,'result':['notify',bytes(200).hex(),
                     (1<<200).to_bytes(32,'little').hex(),bytes(8).hex(),'3']}))
                if not ready.wait(5):raise RuntimeError('worker did not submit')
                return b''.join(encode({'id':r['id'],'status':1,'result':True})
                    for r in self.packets if r['method']in('report_info','submit'))
        class Device:
            def start(self,module):events.append('device-start')
            def close(self):events.append('device-close')
        searches=[]
        class Search:
            def __init__(self,context,device,current,**kwargs):
                searches.append(self);self.first=len(searches)==1
                self.context=context;self.cursor=SimpleNamespace(next_tile=0)
                self.plan=SimpleNamespace(count=8388608)
            def __enter__(self):return self
            def __exit__(self,*args):events.append('cache-close')
            def advance(self,n):
                if rollover and self.first:
                    self.cursor.next_tile=self.plan.count;events.append('full-domain');return None,self.cursor
                self.cursor.next_tile=n;events.append('gpu-hit')
                return Hit(self.context.job.generation,0,bytes(32)),self.cursor
        def nonce(job,base,worker,miner,current):return SimpleNamespace(job=job,worker=worker,miner=miner)
        def proof(context,hit,current):
            events.append('proof-checked');rows,cols=plan_for(context.job).indices(0)
            # Deliberately fake proof: this test checks orchestration only.
            return PreparedShare(context.job,0,tuple(rows),tuple(cols),context.worker,
                                 context.miner,hit.digest,b'mock proof')
        stream=Stream()
        actual_receiver=runner.PoolReceiver
        def receiver(*args,**kwargs):return actual_receiver(*args,**kwargs,connect=lambda *a,**k:stream)
        with tempfile.TemporaryDirectory()as folder,ExitStack()as stack:
            report=Path(folder)/'result.json'
            stack.enter_context(patch.object(runner,'PoolReceiver',receiver))
            stack.enter_context(patch.object(runner,'saved_wallet',return_value='synthetic-wallet'))
            stack.enter_context(patch.object(runner,'prepare_base',return_value=SimpleNamespace(job_key=None)))
            stack.enter_context(patch.object(runner,'prepare_nonce',side_effect=nonce))
            stack.enter_context(patch.object(runner,'ProductionCandidateScanner',Device))
            stack.enter_context(patch.object(runner,'NonceSearch',Search))
            stack.enter_context(patch.object(runner,'prepare_share',side_effect=proof))
            stack.enter_context(patch('sys.argv',['mine_bounded','--host','synthetic.example','--port','9000',
                '--login-file','unused','--module','unused','--report',str(report),'--seconds','3']))
            self.assertEqual(runner.main(),0)
            data=json.loads(report.read_text())
            self.assertEqual(data['submitted_shares'],1);self.assertEqual(data['pool_accepted_shares'],1)
            self.assertTrue(data['worker']['joined']);self.assertEqual(data['work']['proofs_checked'],1)
            self.assertEqual(data['connection']['reports']['accepted'],1)
        self.assertTrue(stream.closed)
        expected=['device-start']+(['full-domain','cache-close']if rollover else[])+['gpu-hit','proof-checked','cache-close','device-close']
        self.assertEqual(events,expected)
        self.assertEqual(data['work']['full_nonces'],int(rollover))
        self.assertEqual(data['work']['nonces_started'],1+int(rollover))
        ids=[p['id']for p in stream.packets]
        self.assertEqual(len(ids),len(set(ids)))


if __name__=='__main__':unittest.main()
