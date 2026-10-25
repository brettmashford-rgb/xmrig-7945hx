"""Pinned installer dependency failure and isolated source installation. No network. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import install_v033 as installer

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_dependency_failure_does_not_download_or_create_output(self):
        with tempfile.TemporaryDirectory()as temporary,ExitStack()as stack:
            home=Path(temporary)
            stack.enter_context(patch.object(Path,'home',return_value=home))
            download=stack.enter_context(patch.object(installer,'download'))
            with self.assertRaises(OSError):installer.main()
            download.assert_not_called()
            self.assertFalse((home/'pearlhash-dev-v0.0.33').exists())

    def test_install_from_pinned_source_sets_exact_runtime_and_propagates_exit(self):
        with tempfile.TemporaryDirectory()as temporary,ExitStack()as stack:
            home=Path(temporary);runtime=home/'pearlhash-dev-v0.0.27'
            runtime.mkdir();reference=home/'pearlhash-dev-v0.0.17';reference.mkdir()
            package=b'{"files": []}\n';digest=hashlib.sha256(package).hexdigest()
            previous=home/'pearlhash-dev-v0.0.31';previous.mkdir()
            for folder in (runtime,reference,previous):(folder/'download-manifest.json').write_bytes(package)
            (previous/'cache-gpu-result.json').write_text(json.dumps({'complete':True,
                'gpu_checked':True,'component_timing':{'same_input_transcripts_match':True},'submitted_shares':0}))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
            library.parent.mkdir(parents=True);library.write_bytes(b'fake library')
            old_manifest=json.dumps({'files':[], 'required_cpu_library_sha256':hashlib.sha256(library.read_bytes()).hexdigest()}).encode()
            (previous/'download-manifest.json').write_bytes(old_manifest)
            stack.enter_context(patch.object(installer,'V31',hashlib.sha256(old_manifest).hexdigest()))
            captures=home/'pearlhash-dev/captures';captures.mkdir(parents=True)
            login=captures/'independent-login-synthetic.json'
            login.write_text(json.dumps({'schema':'pearlhash-login-probe-1','error':None,
                'records':[{'direction':'out','json':{'method':'login','params':['synthetic-wallet','worker','agent']}}]}))
            stack.enter_context(patch.object(Path,'home',return_value=home))
            for constant,value in (('V17',digest),('V27',digest)):
                stack.enter_context(patch.object(installer,constant,value))
            stack.enter_context(patch.object(installer,'download',side_effect=lambda name:(ROOT.parent/name).read_bytes()))
            run=stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=7)))
            self.assertEqual(installer.main(),7)
            args=run.call_args.args[0];env=run.call_args.kwargs['env']
            self.assertNotIn('--host',args)
            self.assertTrue(args[2].endswith('tools/check_cooperative_gpu.py'))
            self.assertEqual(env['PYTHONPATH'],':'.join(map(str,(home/'pearlhash-dev-v0.0.33',runtime,reference))))
            self.assertEqual(env['PEARL_HASH_LIBRARY'],str(library))
            self.assertTrue((home/'pearlhash-dev-v0.0.33/tools/check_cooperative_gpu.py').is_file())
            with self.assertRaisesRegex(ValueError,'already exists'):installer.main()


if __name__=='__main__':unittest.main()
