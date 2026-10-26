"""Fresh resident correctness/proof gate before offline benchmark. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v045 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.44';previous.mkdir()
            completed={'complete':True,'error':None,'pool_connection':False,'submitted_shares':0,
                'loop_comparison':{'rounds':20,'unique_timed_tiles_per_mode':1310720}}
            if mode=='bad-previous':completed['complete']=False
            (previous/'loop-comparison.json').write_text(json.dumps(completed))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test source\n';package=json.dumps({'files':[{'path':'tools/check_resident_job.py',
                'repository_path':'pearlhash/tools/check_resident_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
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
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,target_cases=18,
                        descriptor_windows=4,cpu_samples=8,partial_queue_checked=True,official_cpu_verifier='passed',
                        retained_windows_and_stale_rejected=True)
                    if mode=='bad-gate':report['official_cpu_verifier']='failed'
                    (out/'manifest.json').write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode=='bad-previous':
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode=='bad-gate':
                with self.assertRaisesRegex(ValueError,'correctness gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode=='process-failure':self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1)
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,13);self.assertEqual(len(calls),2)
                self.assertTrue(calls[0][2].endswith('check_resident_job.py'))
                self.assertTrue(calls[1][2].endswith('compare_resident_loops.py'))
                self.assertIn('--oracle',calls[0])
    def test_new_proof_then_offline_comparison(self):self.exercise('ok')
    def test_bad_proof_blocks_timing(self):self.exercise('bad-gate')
    def test_gpu_failure_blocks_timing(self):self.exercise('process-failure')
    def test_bad_previous_result_blocks_work(self):self.exercise('bad-previous')


if __name__=='__main__':unittest.main()
