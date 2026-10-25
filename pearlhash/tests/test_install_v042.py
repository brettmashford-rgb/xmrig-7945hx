"""Fail-closed paired proof gate before one bounded live invocation. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v042 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.41';previous.mkdir()
            (previous/'stream-comparison.json').write_text(json.dumps({'complete':True,'error':None,'pool_connection':False,
                'submitted_shares':0,'cases':[{'passed':True}]*15,
                'stream_comparison':{'rounds':20,'preferred':'two-streams','speedup':1.0816}}))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test source\n';package=json.dumps({'files':[{'path':'tools/check_dual_job.py',
                'repository_path':'pearlhash/tools/check_dual_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'find_login',return_value=home/'local-login'))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            calls=[]
            def run(args,**kwargs):
                calls.append((args,kwargs))
                if len(calls)==1:
                    if mode=='process-failure':return SimpleNamespace(returncode=1)
                    output=Path(args[args.index('--output-dir')+1]);output.mkdir()
                    report=dict(complete=True,error=None,official_cpu_verifier='passed',pool_connection=False,submitted_shares=0,
                        retained_two_windows=True,single_tail_passed=True,inflight_stale_pair_rejected=True,stale_proof_rejected=True)
                    if mode=='missing-gate':report.pop('inflight_stale_pair_rejected')
                    (output/'manifest.json').write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode=='bad-previous':
                (previous/'stream-comparison.json').write_text('{"complete":false}')
                with self.assertRaisesRegex(ValueError,'v041'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode=='missing-gate':
                with self.assertRaisesRegex(ValueError,'lifecycle gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode=='process-failure':
                self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1)
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(len(calls),2)
                args,kwargs=calls[1]
                for flag in ('--cache-a','--two-streams','--seconds','--report'):self.assertIn(flag,args)
                self.assertEqual(args[args.index('--seconds')+1],'300')
                self.assertEqual(args[args.index('--host')+1],'pool.pearlhash.xyz')
                self.assertEqual(kwargs['env']['PYTHONPATH'].split(':')[0],str(home/'pearlhash-dev-v0.0.42'))
    def test_new_proof_gate_then_single_bounded_dual_attempt(self):self.exercise('ok')
    def test_missing_stale_gate_blocks_live(self):self.exercise('missing-gate')
    def test_preflight_failure_blocks_live(self):self.exercise('process-failure')
    def test_bad_previous_result_blocks_download_and_gpu(self):self.exercise('bad-previous')


if __name__=='__main__':unittest.main()
