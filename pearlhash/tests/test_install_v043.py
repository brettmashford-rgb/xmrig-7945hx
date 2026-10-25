"""Completed dual run required; offline comparison cannot invoke live miner. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v043 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.42';(previous/'offline-preflight').mkdir(parents=True)
            complete={'complete':True,'error':None,'worker':{'joined':True},'scan_backend':'cached-a-two-streams-v042'}
            preflight={'complete':True,'error':None,'official_cpu_verifier':'passed','retained_two_windows':True,
                'single_tail_passed':True,'inflight_stale_pair_rejected':True,'stale_proof_rejected':True}
            if mode=='unfinished':complete['worker']['joined']=False
            if mode=='bad-proof':preflight['official_cpu_verifier']='failed'
            (previous/'mining-result.json').write_text(json.dumps(complete))
            (previous/'offline-preflight/manifest.json').write_text(json.dumps(preflight))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test source\n';package=json.dumps({'files':[{'path':'tools/compare_search_loops.py',
                'repository_path':'pearlhash/tools/compare_search_loops.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            run=stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0)))
            if mode!='ok':
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();run.assert_not_called()
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,11);self.assertEqual(run.call_count,1)
                args=run.call_args.args[0];self.assertIn('--report',args);self.assertNotIn('--host',args)
                self.assertNotIn('--login-file',args);self.assertTrue(args[2].endswith('compare_search_loops.py'))
                self.assertEqual(run.call_args.kwargs['env']['PYTHONPATH'].split(':')[0],str(home/'pearlhash-dev-v0.0.43'))
    def test_single_offline_invocation(self):self.exercise('ok')
    def test_unjoined_live_worker_blocks_work(self):self.exercise('unfinished')
    def test_bad_previous_proof_blocks_work(self):self.exercise('bad-proof')


if __name__=='__main__':unittest.main()
