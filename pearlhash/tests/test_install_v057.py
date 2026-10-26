"""Single fresh early-only proof/correctness gate before the paired offline timing. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v057 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp)
            def write(path,data):
                path=home/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
            live=dict(complete=True,error=None,worker={'joined':True},scan_backend='quad5-one-stream-v054')
            if mode=='live-failed':live['complete']=False
            if mode=='live-not-joined':live['worker']['joined']=False
            write('pearlhash-dev-v0.0.54/mining-result.json',live)
            previous=dict(complete=mode!='prior-offline',error=None,pool_connection=False,submitted_shares=0,
                tests={'test1':{},'test2':{}})
            write('pearlhash-dev-v0.0.55/two-test-summary.json',previous)
            latest=dict(complete=mode!='prior-latest',error=None,pool_connection=False,submitted_shares=0,
                readback_contract_checked=True,loop_comparison={'descriptor_path':'early-only-v056'})
            write('pearlhash-dev-v0.0.56/early-only-comparison.json',latest)
            completed=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,readback_contract_checked=True,
                loop_comparison=dict(rounds=24,unique_timed_tiles_per_mode=1572864,preferred='quad5-v052',
                    descriptor_path='four-row-b-quad-v052',speedup_over_v051={'quad5-v052':1.29598}))
            prior=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,modes_checked=2,
                official_cpu_verifiers=2,transcript_windows=8,cpu_samples=16,target_cases=36,guard_cases=56,
                partial_queue_checked=True,retained_windows_and_stale_rejected=True)
            if mode=='previous-proof':prior['official_cpu_verifiers']=1
            write('pearlhash-dev-v0.0.52/b-quad-comparison.json',completed)
            write('pearlhash-dev-v0.0.52/offline-preflight/manifest.json',prior)
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test source\n';package=json.dumps({'files':[{'path':'tools/check_b_transpose_job.py',
                'repository_path':'pearlhash/tools/check_b_transpose_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            calls=[]
            def run(args,**kwargs):
                calls.append(args);self.assertNotIn('--host',args)
                if len(calls)==1:
                    if mode=='process-failure':return SimpleNamespace(returncode=1)
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,target_cases=18,
                        transcript_windows=4,cpu_samples=8,modes_checked=1,guard_cases=28,partial_queue_checked=True,
                        official_cpu_verifiers=1,retained_windows_and_stale_rejected=True)
                    if mode=='bad-proof':report['official_cpu_verifiers']=0
                    if mode=='missing-guard':report['guard_cases']=27
                    if mode=='missing-stale':report['retained_windows_and_stale_rejected']=False
                    if mode=='pool-connection':report['pool_connection']=True
                    if mode=='missing-window':report['transcript_windows']=3
                    out=Path(args[args.index('--output-dir')+1]);out.mkdir();(out/'manifest.json').write_text(json.dumps(report))
                else:
                    if mode=='timing-fails':return SimpleNamespace(returncode=1)
                    report=dict(complete=mode!='bad-timing',error=None,pool_connection=False,submitted_shares=0,
                        readback_contract_checked=True,loop_comparison=dict(rounds=24,
                            unique_timed_tiles_per_mode=1572864,descriptor_path='b-transpose-v057'))
                    Path(args[args.index('--report')+1]).write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode in ('live-failed','live-not-joined','prior-offline','prior-latest','previous-proof'):
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode in ('bad-proof','missing-guard','missing-stale','pool-connection','missing-window'):
                with self.assertRaisesRegex(ValueError,'correctness gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode in ('process-failure','timing-fails'):
                self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1 if mode=='process-failure'else 2)
            elif mode=='bad-timing':
                with self.assertRaisesRegex(ValueError,'comparison completion differs'):installer.main()
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,25);self.assertEqual(len(calls),2)
                self.assertTrue(calls[0][2].endswith('check_b_transpose_job.py'))
                self.assertTrue(calls[1][2].endswith('compare_b_transpose_loops.py'))
                self.assertIn('--oracle',calls[0]);self.assertEqual(calls[1][calls[1].index('--variant')+1],'transpose')
                self.assertEqual(calls[0][calls[0].index('--module')+1],str(home/'pearlhash-dev-v0.0.57/releases/pearlhash-dev-v0.0.57-scan-sm120.ptx'))
    def test_fresh_proof_then_early_only_comparison(self):self.exercise('ok')
    def test_failed_live_blocks_gpu_work(self):self.exercise('live-failed')
    def test_unjoined_live_blocks_gpu_work(self):self.exercise('live-not-joined')
    def test_incomplete_prior_experiment_blocks_work(self):self.exercise('prior-offline')
    def test_incomplete_latest_experiment_blocks_work(self):self.exercise('prior-latest')
    def test_previous_proof_blocks_work(self):self.exercise('previous-proof')
    def test_missing_fresh_proof_blocks_timing(self):self.exercise('bad-proof')
    def test_guard_failure_blocks_timing(self):self.exercise('missing-guard')
    def test_stale_failure_blocks_timing(self):self.exercise('missing-stale')
    def test_pool_connection_blocks_timing(self):self.exercise('pool-connection')
    def test_missing_full_window_blocks_timing(self):self.exercise('missing-window')
    def test_preflight_process_failure_blocks_timing(self):self.exercise('process-failure')
    def test_timing_process_failure_is_reported(self):self.exercise('timing-fails')
    def test_bad_timing_report_rejected(self):self.exercise('bad-timing')


if __name__=='__main__':unittest.main()
