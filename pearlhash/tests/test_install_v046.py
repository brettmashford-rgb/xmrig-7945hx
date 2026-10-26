"""Completed resident proof/performance required before bounded live run. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v046 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.45';(previous/'offline-preflight').mkdir(parents=True)
            completed={'complete':True,'error':None,'pool_connection':False,'submitted_shares':0,'loop_comparison':{
                'rounds':20,'unique_timed_tiles_per_mode':1310720,'preferred':'resident-one-stream',
                'descriptor_path':'resident-maps-gpu-built-v045','speedup_resident_over_baseline':1.338}}
            preflight=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,official_cpu_verifier='passed',
                target_cases=18,descriptor_windows=4,cpu_samples=8,partial_queue_checked=True,retained_windows_and_stale_rejected=True)
            if mode=='failed-proof':preflight['official_cpu_verifier']='failed'
            if mode=='no-win':completed['loop_comparison']['speedup_resident_over_baseline']=1.01
            if mode=='missing-stale':preflight.pop('retained_windows_and_stale_rejected')
            (previous/'resident-comparison.json').write_text(json.dumps(completed))
            (previous/'offline-preflight/manifest.json').write_text(json.dumps(preflight))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test runner\n';package=json.dumps({'files':[{'path':'tools/mine_bounded.py',
                'repository_path':'pearlhash/tools/mine_bounded.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            stack.enter_context(patch.object(installer,'find_login',return_value=home/'local-login'))
            run=stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0)))
            if mode!='ok':
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();run.assert_not_called()
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,14);self.assertEqual(run.call_count,1)
                args=run.call_args.args[0]
                for flag in ('--cache-a','--resident-maps','--commitment-module'):self.assertIn(flag,args)
                self.assertNotIn('--two-streams',args);self.assertNotIn('--oracle',args)
                self.assertEqual(args[args.index('--seconds')+1],'300')
                self.assertEqual(args[args.index('--host')+1],'pool.pearlhash.xyz')
                self.assertEqual(args[args.index('--module')+1],str(previous/'releases/pearlhash-dev-v0.0.45-scan-sm120.ptx'))
                self.assertEqual(run.call_args.kwargs['env']['PYTHONPATH'].split(':')[0],str(home/'pearlhash-dev-v0.0.46'))
    def test_single_bounded_resident_run_without_repeating_gpu_tests(self):self.exercise('ok')
    def test_failed_proof_blocks_download_and_live_connection(self):self.exercise('failed-proof')
    def test_no_clear_timing_win_blocks_live_connection(self):self.exercise('no-win')
    def test_missing_stale_gate_blocks_live_connection(self):self.exercise('missing-stale')


if __name__=='__main__':unittest.main()
