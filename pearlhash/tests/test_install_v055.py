"""Fresh resident correctness/proof gate before offline benchmark. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v055 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.52';previous.mkdir()
            live=dict(complete=True,error=None,worker={'joined':True},scan_backend='quad5-one-stream-v054')
            if mode=='live-failed':live['complete']=False
            if mode=='live-not-joined':live['worker']['joined']=False
            if mode=='live-wrong-backend':live['scan_backend']='lean-direct-one-stream-v051'
            live_folder=home/'pearlhash-dev-v0.0.54';live_folder.mkdir()
            (live_folder/'mining-result.json').write_text(json.dumps(live))
            completed={'complete':True,'error':None,'pool_connection':False,'submitted_shares':0,
                'readback_contract_checked':True,'loop_comparison':{'rounds':24,
                    'unique_timed_tiles_per_mode':1572864,'preferred':'quad5-v052',
                    'descriptor_path':'four-row-b-quad-v052','speedup_over_v051':{'quad5-v052':1.29598}}}
            prior=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,modes_checked=2,
                official_cpu_verifiers=2,transcript_windows=8,cpu_samples=16,target_cases=36,
                guard_cases=56,partial_queue_checked=True,retained_windows_and_stale_rejected=True)
            if mode=='bad-previous':completed['complete']=False
            if mode=='previous-proof':prior['official_cpu_verifiers']=1
            if mode=='previous-margin':completed['loop_comparison']['speedup_over_v051']['quad5-v052']=1.01
            if mode=='previous-driver':completed['readback_contract_checked']=False
            (previous/'b-quad-comparison.json').write_text(json.dumps(completed))
            (previous/'offline-preflight').mkdir()
            (previous/'offline-preflight/manifest.json').write_text(json.dumps(prior))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test source\n';package=json.dumps({'files':[{'path':'tools/check_b_loop_job.py',
                'repository_path':'pearlhash/tools/check_b_loop_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            calls=[]
            def run(args,**kwargs):
                calls.append(args);self.assertNotIn('--host',args)
                if len(calls)==1:
                    if mode=='process-failure':return SimpleNamespace(returncode=1)
                    out=Path(args[args.index('--output-dir')+1]);out.mkdir()
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,target_cases=36,
                        transcript_windows=8,cpu_samples=16,modes_checked=2,guard_cases=56,partial_queue_checked=True,official_cpu_verifiers=2,
                        retained_windows_and_stale_rejected=True)
                    if mode=='bad-gate':report['official_cpu_verifiers']=1
                    if mode=='missing-guard':report['guard_cases']=55
                    if mode=='pool-connection':report['pool_connection']=True
                    if mode=='second-path-missing':report['modes_checked']=1
                    (out/'manifest.json').write_text(json.dumps(report))
                else:
                    if mode=='first-timing-fails'and len(calls)==2:return SimpleNamespace(returncode=1)
                    if mode=='second-timing-fails'and len(calls)==3:return SimpleNamespace(returncode=1)
                    variant=args[args.index('--variant')+1]
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                        readback_contract_checked=True,kernel_resources={},loop_comparison={
                            'rounds':24,'unique_timed_tiles_per_mode':1572864,
                            'descriptor_path':'b-loop-'+variant+'-v055','median_tiles_per_second':{},
                            'speedup_over_quad5':{},'preferred':'quad5-v054'})
                    if mode=='bad-first-timing'and len(calls)==2:report['complete']=False
                    if mode=='bad-second-timing'and len(calls)==3:report['readback_contract_checked']=False
                    Path(args[args.index('--report')+1]).write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode in ('live-failed','live-not-joined','live-wrong-backend','bad-previous','previous-proof','previous-margin','previous-driver'):
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode in ('bad-gate','missing-guard','pool-connection','second-path-missing'):
                with self.assertRaisesRegex(ValueError,'correctness gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode in ('first-timing-fails','second-timing-fails'):
                self.assertEqual(installer.main(),1);self.assertEqual(len(calls),2 if mode=='first-timing-fails'else 3)
                self.assertFalse((home/'pearlhash-dev-v0.0.55/two-test-summary.json').exists())
            elif mode in ('bad-first-timing','bad-second-timing'):
                with self.assertRaisesRegex(ValueError,'comparison completion differs'):installer.main()
                self.assertEqual(len(calls),2 if mode=='bad-first-timing'else 3)
            elif mode=='process-failure':self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1)
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,23);self.assertEqual(len(calls),3)
                self.assertTrue(calls[0][2].endswith('check_b_loop_job.py'))
                self.assertTrue(calls[1][2].endswith('compare_b_loop_loops.py'))
                self.assertTrue(calls[2][2].endswith('compare_b_loop_loops.py'))
                self.assertEqual([c[c.index('--variant')+1]for c in calls[1:]],['grouped','early'])
                self.assertIn('--oracle',calls[0])
                summary=json.loads((home/'pearlhash-dev-v0.0.55/two-test-summary.json').read_text())
                self.assertTrue(summary['complete']);self.assertEqual(set(summary['tests']),{'test1','test2'})
                self.assertEqual(calls[0][calls[0].index('--module')+1],str(home/'pearlhash-dev-v0.0.55/releases/pearlhash-dev-v0.0.55-scan-sm120.ptx'))
    def test_live_failure_blocks_gpu_work(self):self.exercise('live-failed')
    def test_unjoined_live_worker_blocks_gpu_work(self):self.exercise('live-not-joined')
    def test_wrong_live_backend_blocks_gpu_work(self):self.exercise('live-wrong-backend')
    def test_first_timing_failure_blocks_second_test(self):self.exercise('first-timing-fails')
    def test_second_timing_failure_does_not_publish_success(self):self.exercise('second-timing-fails')
    def test_bad_first_timing_report_blocks_second_test(self):self.exercise('bad-first-timing')
    def test_bad_second_timing_report_blocks_success(self):self.exercise('bad-second-timing')
    def test_new_proof_then_offline_comparison(self):self.exercise('ok')
    def test_bad_proof_blocks_timing(self):self.exercise('bad-gate')
    def test_gpu_failure_blocks_timing(self):self.exercise('process-failure')
    def test_missing_guard_blocks_timing(self):self.exercise('missing-guard')
    def test_pool_connection_blocks_timing(self):self.exercise('pool-connection')
    def test_missing_second_path_blocks_timing(self):self.exercise('second-path-missing')
    def test_bad_previous_proof_blocks_work(self):self.exercise('previous-proof')
    def test_bad_previous_margin_blocks_work(self):self.exercise('previous-margin')
    def test_bad_previous_driver_blocks_work(self):self.exercise('previous-driver')
    def test_bad_previous_result_blocks_work(self):self.exercise('bad-previous')


if __name__=='__main__':unittest.main()
