"""No-network install integrity, dependency and runtime propagation checks. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v035 as installer

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_missing_completion_stops_before_download_or_creation(self):
        with tempfile.TemporaryDirectory()as temporary:
            home=Path(temporary)
            with patch.object(Path,'home',return_value=home),patch.object(installer,'download')as download:
                with self.assertRaises(OSError):installer.main()
                download.assert_not_called()
                self.assertFalse((home/'pearlhash-dev-v0.0.35').exists())

    def test_install_checks_source_and_exact_runtime_then_propagates_exit(self):
        with tempfile.TemporaryDirectory()as temporary,ExitStack()as stack:
            home=Path(temporary)
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
            library.parent.mkdir(parents=True);library.write_bytes(b'synthetic library')
            for version in ('33','31','27','17'):
                folder=home/('pearlhash-dev-v0.0.'+version);folder.mkdir()
                manifest={'files':[]}
                if version=='31':manifest['required_cpu_library_sha256']=hashlib.sha256(library.read_bytes()).hexdigest()
                raw=json.dumps(manifest).encode();(folder/'download-manifest.json').write_bytes(raw)
                stack.enter_context(patch.object(installer,'V'+version,hashlib.sha256(raw).hexdigest()))
            previous=home/'pearlhash-dev-v0.0.34';(previous/'tools').mkdir(parents=True)
            profiler=(ROOT/'tools/profile_dispatch.py').read_bytes()
            (previous/'tools/profile_dispatch.py').write_bytes(profiler)
            (previous/'dispatch-profile-result.json').write_text(json.dumps({'complete':True,'submitted_shares':0,
                'transcripts_match':True,'rounds':{label:[{}]*8 for label in ('virtual','fragment','cooperative')}}))
            stack.enter_context(patch.object(Path,'home',return_value=home))
            download=stack.enter_context(patch.object(installer,'download',side_effect=lambda name:(ROOT.parent/name).read_bytes()))
            run=stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=7)))
            self.assertEqual(installer.main(),7)
            self.assertEqual(download.call_count,5)
            args=run.call_args.args[0];env=run.call_args.kwargs['env']
            self.assertTrue(args[2].endswith('tools/check_prepared_gpu.py'))
            self.assertTrue(args[4].endswith('v0.0.33-sm120.ptx'))
            self.assertEqual(env['PYTHONPATH'],':'.join(str(home/('pearlhash-dev-v0.0.'+v))for v in ('35','34','33','27','17')))
            self.assertEqual(env['PEARL_HASH_LIBRARY'],str(library))
            self.assertEqual((home/'pearlhash-dev-v0.0.35/tools/prepared_dispatch.py').read_bytes(),(ROOT/'tools/prepared_dispatch.py').read_bytes())
            with self.assertRaisesRegex(ValueError,'already exists'):installer.main()


if __name__=='__main__':unittest.main()
