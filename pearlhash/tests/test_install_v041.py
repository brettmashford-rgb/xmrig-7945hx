"""Pinned dependency/completion gates and offline-only invocation. ISC."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v041 as installer


class Installer(unittest.TestCase):
    def prepare(self,home):
        folder=home/'pearlhash-dev-v0.0.40';(folder/'offline-preflight').mkdir(parents=True)
        (folder/'offline-preflight/manifest.json').write_text(json.dumps({'complete':True,'error':None,
            'official_cpu_verifier':'passed','scan_comparison':{'preferred':'cached-a'}}))
        (folder/'mining-result.json').write_text(json.dumps({'complete':True,'error':None,'worker':{'joined':True},
            'scan_backend':'cached-a-virtual-b-v040'}))
        library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test library')
        return {'required_cpu_library_sha256':hashlib.sha256(library.read_bytes()).hexdigest()}
    def test_offline_invocation_and_source_pinning(self):
        with tempfile.TemporaryDirectory()as temp:
            home=Path(temp);dependency=self.prepare(home);source=b'print("offline")\n'
            manifest=json.dumps({'files':[{'path':'tools/check_streams.py','repository_path':'pearlhash/tools/check_streams.py',
                'bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            with patch.object(Path,'home',return_value=home),patch.object(installer,'verify_package',return_value=dependency)as verify,\
                 patch.object(installer,'MANIFEST',hashlib.sha256(manifest).hexdigest()),\
                 patch.object(installer,'download',side_effect=[manifest,source]),\
                 patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0))as run:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,9)
                args=run.call_args.args[0];self.assertIn('--report',args);self.assertNotIn('--host',args)
                self.assertIn('v0.0.40-scan-sm120.ptx',' '.join(args))
                self.assertEqual(run.call_args.kwargs['env']['PYTHONPATH'].split(':')[0],str(home/'pearlhash-dev-v0.0.41'))
                with self.assertRaisesRegex(ValueError,'already exists'):installer.main()
    def test_unjoined_worker_blocks_download_and_gpu(self):
        with tempfile.TemporaryDirectory()as temp:
            home=Path(temp);dependency=self.prepare(home)
            (home/'pearlhash-dev-v0.0.40/mining-result.json').write_text('{"complete":true,"worker":{"joined":false}}')
            with patch.object(Path,'home',return_value=home),patch.object(installer,'verify_package',return_value=dependency),\
                 patch.object(installer,'download')as download,patch.object(installer.subprocess,'run')as run:
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();run.assert_not_called()
    def test_dependency_corruption_blocks_all_gpu_work(self):
        with tempfile.TemporaryDirectory()as temp:
            home=Path(temp)
            with patch.object(Path,'home',return_value=home),patch.object(installer.subprocess,'run')as run:
                with self.assertRaises(OSError):installer.main()
                run.assert_not_called()


if __name__=='__main__':unittest.main()
