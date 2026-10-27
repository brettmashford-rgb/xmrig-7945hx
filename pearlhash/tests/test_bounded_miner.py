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

    def test_cached_a_option_is_recorded_in_live_worker(self):
        self.run_attempt(False,gpu=True,cached=True)

    def test_two_stream_option_uses_paired_search_and_truthful_metadata(self):
        self.run_attempt(False,gpu=True,cached=True,dual=True)

    def test_resident_maps_uses_verified_search_and_truthful_metadata(self):
        self.run_attempt(False,gpu=True,cached=True,resident=True)

    def test_resident_maps_rolls_over_full_nonce(self):
        self.run_attempt(True,gpu=True,cached=True,resident=True)

    def test_packed_direct_uses_validated_path_and_truthful_metadata(self):
        self.run_attempt(False,gpu=True,cached=True,packed=True)

    def test_packed_direct_rolls_over_full_nonce(self):
        self.run_attempt(True,gpu=True,cached=True,packed=True)

    def test_packed_direct_status_acknowledgement_is_not_an_accepted_share(self):
        self.run_attempt(False,gpu=True,cached=True,packed=True,no_hit=True)

    def test_lean_direct_uses_verified_search_and_truthful_metadata(self):
        self.run_attempt(False,gpu=True,cached=True,lean=True)

    def test_lean_direct_rolls_over_full_nonce(self):
        self.run_attempt(True,gpu=True,cached=True,lean=True)

    def test_lean_status_acknowledgement_is_not_an_accepted_share(self):
        self.run_attempt(False,gpu=True,cached=True,lean=True,no_hit=True)

    def test_quad5_uses_validated_padded_search_and_truthful_metadata(self):
        self.run_attempt(False,gpu=True,cached=True,quad=True)

    def test_quad5_rolls_over_full_nonce(self):
        self.run_attempt(True,gpu=True,cached=True,quad=True)

    def test_quad5_status_acknowledgement_is_not_an_accepted_share(self):
        self.run_attempt(False,gpu=True,cached=True,quad=True,no_hit=True)

    def test_job_B_cache_rollover_reuses_owner_and_cached_nonce(self):
        self.run_attempt(True,gpu=True,cached=True,jobcache=True)

    def test_job_B_cache_candidate_still_uses_submission_gate(self):
        self.run_attempt(False,gpu=True,cached=True,jobcache=True)

    def test_job_B_cache_status_ack_is_not_a_share(self):
        self.run_attempt(False,gpu=True,cached=True,jobcache=True,no_hit=True)

    def test_incompatible_scan_flags_fail_before_any_pool_work(self):
        with patch.object(runner,'PoolReceiver')as receiver:
            for flags in (['--job-b-cache'],['--job-b-cache','--quad5','--cache-a'],['--quad5'],['--quad5','--lean-direct','--cache-a'],
                    ['--quad5','--packed-direct','--cache-a'],['--quad5','--resident-maps','--cache-a'],
                    ['--quad5','--two-streams','--cache-a'],['--resident-maps'],['--packed-direct'],
                    ['--resident-maps','--two-streams','--cache-a'],
                    ['--packed-direct','--resident-maps','--cache-a'],
                    ['--packed-direct','--two-streams','--cache-a'],['--lean-direct'],
                    ['--lean-direct','--packed-direct','--cache-a'],
                    ['--lean-direct','--resident-maps','--cache-a'],
                    ['--lean-direct','--two-streams','--cache-a']):
                with patch('sys.argv',['mine_bounded','--host','synthetic.example','--port','9000',
                        '--login-file','unused','--module','unused','--report','unused']+flags):
                    with self.assertRaises((ValueError,SystemExit)):runner.main()
            receiver.assert_not_called()

    def test_gpu_base_option_uses_new_commitment_helper(self):
        self.run_attempt(False,gpu=True)

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

    def run_attempt(self,rollover,gpu=False,cached=False,dual=False,resident=False,packed=False,no_hit=False,lean=False,quad=False,jobcache=False):
        events=[];ready=threading.Event();scanned=threading.Event();finished=threading.Event()
        class Stream:
            def __init__(self):self.packets=[];self.step=0;self.timeout=1;self.closed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def settimeout(self,value):self.timeout=value
            def gettimeout(self):return self.timeout
            def sendall(self,data):
                request=decode(data);self.packets.append(request)
                if request['method']=='submit' or(no_hit and request['method']=='report_info'):ready.set()
            def recv(self,size):
                self.step+=1
                if self.step==1:return b''.join(encode(x)for x in (
                    {'id':0,'status':1,'result':True},
                    {'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]},
                    {'id':-1,'status':1,'result':['notify',bytes(200).hex(),
                     (1<<200).to_bytes(32,'little').hex(),bytes(8).hex(),'3']}))
                if no_hit and self.step>=3:finished.set();return b''
                if not ready.wait(5):raise RuntimeError('worker did not submit')
                if no_hit and not scanned.wait(5):raise RuntimeError('worker did not scan')
                return b''.join(encode({'id':r['id'],'status':1,'result':True})
                    for r in self.packets if r['method']in('report_info','submit'))
        class Device:
            def start(self,module):events.append('device-start')
            def close(self):events.append('device-close')
        searches=[];search_kwargs=[]
        class Search:
            def __init__(self,context,device,current,**kwargs):
                search_kwargs.append(kwargs);searches.append(self);self.first=len(searches)==1
                self.context=context;self.current=current;self.cursor=SimpleNamespace(next_tile=0)
                self.plan=SimpleNamespace(count=8388608)
            def __enter__(self):return self
            def __exit__(self,*args):events.append('cache-close')
            def advance(self,n):
                if no_hit:
                    runner.require_current(self.context.job,self.current)
                    self.cursor.next_tile+=n;scanned.set()
                    if not finished.wait(5):raise RuntimeError('scripted receiver did not finish')
                    runner.require_current(self.context.job,self.current)
                    return None,self.cursor
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
            gpu_base=stack.enter_context(patch.object(runner,'prepare_gpu_base',return_value=SimpleNamespace(job_key=None)))
            old_nonce=stack.enter_context(patch.object(runner,'prepare_nonce',side_effect=nonce))
            frontier=stack.enter_context(patch.object(runner.NonceCommitmentCache,'build',return_value=object()))
            cached_nonce=stack.enter_context(patch.object(runner,'prepare_cached_nonce',side_effect=lambda *a:nonce(*a[:5])))
            owner=stack.enter_context(patch.object(runner,'JobBTables'))
            owner.return_value.stats.return_value=dict(b_table_builds=1,b_table_leases=1+int(rollover),
                b_table_generated_bytes=33685504,b_table_setup_seconds=.01,closed=True)
            job_search=stack.enter_context(patch.object(runner,'new_job_b_search',side_effect=lambda c,d,cur,o,**kw:Search(c,d,cur,**kw)))
            stack.enter_context(patch.object(runner,'ProductionCandidateScanner',Device))
            stack.enter_context(patch.object(runner,'NonceSearch',Search))
            stack.enter_context(patch.object(runner,'DualSearch',Search))
            resident_search=stack.enter_context(patch.object(runner,'new_resident_search',side_effect=Search))
            packed_search=stack.enter_context(patch.object(runner,'new_snapshot_search',side_effect=Search))
            quad_search=stack.enter_context(patch.object(runner,'new_b_quad_search',side_effect=Search))
            lean_search=stack.enter_context(patch.object(runner,'new_lean_search',side_effect=Search))
            stack.enter_context(patch.object(runner,'prepare_share',side_effect=proof))
            stack.enter_context(patch('sys.argv',['mine_bounded','--host','synthetic.example','--port','9000',
                '--login-file','unused','--module','unused','--report',str(report),'--seconds','3']+(['--commitment-module','unused-commitment']if gpu else [])+(['--cache-a']if cached else [])+(['--two-streams']if dual else [])+(['--resident-maps']if resident else [])+(['--packed-direct']if packed else [])+(['--lean-direct']if lean else [])+(['--quad5']if quad else [])+(['--job-b-cache']if jobcache else [])))
            self.assertEqual(runner.main(),0)
            self.assertEqual(gpu_base.call_count,int(gpu))
            self.assertEqual(packed_search.call_count,(1+int(rollover))if packed else 0)
            self.assertEqual(resident_search.call_count,(1+int(rollover))if resident else 0)
            self.assertEqual(lean_search.call_count,(1+int(rollover))if lean else 0)
            self.assertEqual(quad_search.call_count,(1+int(rollover))if quad else 0)
            if jobcache:
                self.assertEqual(owner.call_count,1);self.assertEqual(owner.return_value.close.call_count,1)
                self.assertEqual(frontier.call_count,1);self.assertEqual(cached_nonce.call_count,1+int(rollover))
                self.assertEqual(old_nonce.call_count,0);self.assertEqual(job_search.call_count,1+int(rollover))
            if quad:self.assertTrue(all(k.get('padded')is True for k in search_kwargs))
            if lean:self.assertTrue(all(k.get('lean')is True for k in search_kwargs))
            if packed:self.assertTrue(all(k.get('direct')is True for k in search_kwargs))
            data=json.loads(report.read_text())
            self.assertEqual(data['commitment_backend'],'gpu-constant-v039'if gpu else 'cpu-streaming')
            self.assertEqual(data['scan_backend'],'shared-B-job-cache-one-stream-v062'if jobcache else 'quad5-one-stream-v054'if quad else 'lean-direct-one-stream-v051'if lean else 'packed-direct-one-stream-v049'if packed else 'resident-maps-one-stream-v046'if resident else 'cached-a-two-streams-v042'if dual else 'cached-a-virtual-b-v040'if cached else 'validated-axis-production-virtual-v038')
            self.assertEqual(data['submitted_shares'],int(not no_hit));self.assertEqual(data['pool_accepted_shares'],int(not no_hit))
            self.assertEqual(data['extranonce_worker_role_verified'],not no_hit)
            self.assertTrue(data['worker']['joined']);self.assertEqual(data['work']['proofs_checked'],int(not no_hit))
            self.assertEqual(data['connection']['reports']['accepted'],1)
        self.assertTrue(stream.closed)
        expected=['device-start','cache-close','device-close']if no_hit else ['device-start']+(['full-domain','cache-close']if rollover else[])+['gpu-hit','proof-checked','cache-close','device-close']
        self.assertEqual(events,expected)
        self.assertEqual(data['work']['full_nonces'],int(rollover))
        self.assertEqual(data['work']['nonces_started'],1+int(rollover))
        ids=[p['id']for p in stream.packets]
        self.assertEqual(len(ids),len(set(ids)))


if __name__=='__main__':unittest.main()
