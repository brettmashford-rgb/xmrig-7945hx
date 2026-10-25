"""Production profiler installer dependencies, integrity and exact runtime. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v037 as installer
ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_missing_completion_never_downloads_or_starts(self):
        with tempfile.TemporaryDirectory()as temporary:
            home=Path(temporary)
            with patch.object(Path,'home',return_value=home),patch.object(installer,'download')as download:
                with self.assertRaises(OSError):installer.main()
                download.assert_not_called();self.assertFalse((home/'pearlhash-dev-v0.0.37').exists())

    def test_verified_install_uses_diagnostic_only_and_propagates_exit(self):
        with tempfile.TemporaryDirectory()as temporary,ExitStack()as stack:
            home=Path(temporary);library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
            library.parent.mkdir(parents=True);library.write_bytes(b'synthetic library')
            for version in ('36','35','33','31','27','17'):
                folder=home/('pearlhash-dev-v0.0.'+version);folder.mkdir()
                manifest={'files':[]}
                if version=='31':manifest['required_cpu_library_sha256']=hashlib.sha256(library.read_bytes()).hexdigest()
                raw=json.dumps(manifest).encode();(folder/'download-manifest.json').write_bytes(raw)
                stack.enter_context(patch.object(installer,'V'+version,hashlib.sha256(raw).hexdigest()))
            previous=home/'pearlhash-dev-v0.0.36'
            (previous/'mining-result.json').write_text(json.dumps({'complete':True,'worker':{'joined':True},
                'scan_backend':'prepared-production-virtual-v036'}))
            (previous/'offline-preflight').mkdir()
            (previous/'offline-preflight/manifest.json').write_text(json.dumps({'complete':True,'official_cpu_verifier':'passed'}))
            profiler=home/'pearlhash-dev-v0.0.34/tools/profile_dispatch.py';profiler.parent.mkdir(parents=True)
            profiler.write_bytes((ROOT/'tools/profile_dispatch.py').read_bytes())
            login=home/'pearlhash-dev/captures/independent-login-test.json';login.parent.mkdir(parents=True)
            login.write_text(json.dumps({'schema':'pearlhash-login-probe-1','records':[{'direction':'out',
                'json':{'method':'login','params':['synthetic-wallet','test-worker','test-agent']}}]}))
            stack.enter_context(patch.object(Path,'home',return_value=home))
            download=stack.enter_context(patch.object(installer,'download',return_value=(ROOT/'tools/profile_production.py').read_bytes()))
            run=stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=7)))
            self.assertEqual(installer.main(),7);self.assertEqual(run.call_count,1)
            args=run.call_args.args[0];env=run.call_args.kwargs['env']
            self.assertTrue(args[2].endswith('tools/profile_production.py'))
            self.assertNotIn('mine_bounded.py',' '.join(args))
            self.assertNotIn('--oracle',args)
            self.assertEqual(env['PYTHONPATH'],':'.join(str(home/('pearlhash-dev-v0.0.'+v))for v in ('37','36','35','34','33','27','17')))
            self.assertEqual(env['PEARL_HASH_LIBRARY'],str(library))
            download.assert_called_once_with('pearlhash/tools/profile_production.py')
            with self.assertRaisesRegex(ValueError,'already exists'):installer.main()


if __name__=='__main__':unittest.main()
