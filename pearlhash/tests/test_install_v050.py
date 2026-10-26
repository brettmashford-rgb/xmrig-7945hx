"""Fresh resident correctness/proof gate before offline benchmark. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v050 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.49';previous.mkdir()
            completed={'complete':True,'error':None,'worker':{'joined':True},'scan_backend':'packed-direct-one-stream-v049'}
            if mode=='bad-previous':completed['complete']=False
            (previous/'mining-result.json').write_text(json.dumps(completed))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test source\n';package=json.dumps({'files':[{'path':'tools/check_lean_job.py',
                'repository_path':'pearlhash/tools/check_lean_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
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
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode=='bad-previous':
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode in ('bad-gate','missing-guard','pool-connection','second-path-missing'):
                with self.assertRaisesRegex(ValueError,'correctness gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode=='process-failure':self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1)
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,18);self.assertEqual(len(calls),2)
                self.assertTrue(calls[0][2].endswith('check_lean_job.py'))
                self.assertTrue(calls[1][2].endswith('compare_lean_loops.py'))
                self.assertIn('--oracle',calls[0])
                self.assertEqual(calls[0][calls[0].index('--module')+1],str(home/'pearlhash-dev-v0.0.48/releases/pearlhash-dev-v0.0.48-scan-sm120.ptx'))
    def test_new_proof_then_offline_comparison(self):self.exercise('ok')
    def test_bad_proof_blocks_timing(self):self.exercise('bad-gate')
    def test_gpu_failure_blocks_timing(self):self.exercise('process-failure')
    def test_missing_guard_blocks_timing(self):self.exercise('missing-guard')
    def test_pool_connection_blocks_timing(self):self.exercise('pool-connection')
    def test_missing_second_path_blocks_timing(self):self.exercise('second-path-missing')
    def test_bad_previous_result_blocks_work(self):self.exercise('bad-previous')


if __name__=='__main__':unittest.main()
