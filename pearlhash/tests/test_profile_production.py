"""Real planning coverage, profiler controls and login-only orchestration. ISC."""
from contextlib import ExitStack
import cProfile
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import profile_production as runner
from tools.check_prepared_job import synthetic_session
from tools.wide_scan import wide_plan_for
from tools.pool_probe import encode,decode


class ProfileTests(unittest.TestCase):
    def test_timed_plan_preserves_maps_and_excludes_consumer_time(self):
        session,job,_=synthetic_session(bytes(32));source=wide_plan_for(job)
        timed=runner.TimedPlan(source.a,source.b);timed.batch_queries=64
        with patch.object(runner.time,'perf_counter',side_effect=[0.,1.,10.,12.,20.,23.]):
            iterator=timed.batches(0,100);first=next(iterator)
            self.assertEqual(timed.planning_seconds,1.)
            second=next(iterator);self.assertEqual(timed.planning_seconds,3.)
            with self.assertRaises(StopIteration):next(iterator)
            self.assertEqual(timed.planning_seconds,6.)
        source.batch_queries=64
        self.assertEqual([first,second],list(source.batches(0,100)))
        session.close()

    def test_disabled_measurement_is_plain_and_empty_profile_is_safe(self):
        backend=object.__new__(runner.MeasuredBackend);backend.enabled=False;backend.measurements=[]
        result=object();calls=[]
        def measure(operation):calls.append('measure');return operation(),{'sample':True}
        backend.device=SimpleNamespace(measure=measure)
        with patch.object(runner.PreparedCandidateBackend,'__call__',return_value=result)as operation:
            self.assertIs(backend(1,2,3),result);self.assertEqual(calls,[])
            backend.enabled=True;self.assertIs(backend(1,2,3),result)
            self.assertEqual(operation.call_args.args,(1,2,3))
        self.assertEqual(backend.measurements,[{'sample':True}])
        self.assertEqual(runner.cpu_rows(cProfile.Profile()),[])

    def test_scripted_session_sends_only_login_and_joins_worker(self):
        finished=threading.Event();events=[]
        class Stream:
            def __init__(self):self.packets=[];self.step=0;self.closed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def settimeout(self,value):pass
            def recv(self,size):
                self.step+=1
                if self.step==1:return b''.join(encode(x)for x in (
                    {'id':0,'status':1,'result':True},
                    {'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]},
                    {'id':-1,'status':1,'result':['notify',bytes(200).hex(),(1<<200).to_bytes(32,'little').hex(),bytes(8).hex(),'3']}))
                if not finished.wait(5):raise RuntimeError('diagnostic worker stalled')
                return b''
            def sendall(self,raw):self.packets.append(decode(raw))
        class Device:
            def start(self,path):events.append('start')
            def create_events(self):pass
            def close(self):events.append('close');finished.set()
        class Search:
            def __init__(self,*args,**kwargs):
                self.cursor=SimpleNamespace(next_tile=0);self.plan=SimpleNamespace(planning_seconds=0.)
                self.backend=SimpleNamespace(enabled=False,prepare_seconds=0.,scan_seconds=0.,measurements=[],stats=lambda:{'closed':True})
            def advance(self,tiles):self.cursor.next_tile+=tiles;return None,self.cursor
            def close(self):events.append('search-close')
        stream=Stream();receiver=runner.PoolReceiver
        def connect_receiver(*args,**kwargs):return receiver(*args,**kwargs,connect=lambda *a,**k:stream)
        with tempfile.TemporaryDirectory()as temporary,ExitStack()as stack:
            report=Path(temporary)/'report.json'
            for name,value in (('PoolReceiver',connect_receiver),('ProfileScanner',Device),('NonceSearch',Search)):
                stack.enter_context(patch.object(runner,name,value))
            stack.enter_context(patch.object(runner,'saved_wallet',return_value='synthetic-wallet'))
            stack.enter_context(patch.object(runner,'prepare_base',return_value=object()))
            stack.enter_context(patch.object(runner,'prepare_nonce',return_value=object()))
            stack.enter_context(patch('sys.argv',['profile','--login-file','unused','--module','unused','--report',str(report)]))
            self.assertEqual(runner.main(),0)
            data=json.loads(report.read_text());self.assertTrue(data['worker']['joined'])
            self.assertEqual(data['submitted_shares'],0);self.assertEqual(len(data['jobs'][0]['windows']),32)
            self.assertEqual([request['method']for request in stream.packets],['login'])
            self.assertTrue(stream.closed);self.assertEqual(events,['start','search-close','close'])


if __name__=='__main__':unittest.main()
