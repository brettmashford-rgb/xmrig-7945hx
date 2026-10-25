"""Pinned profiling installer dependency, integrity and subprocess checks. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v034 as installer

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_missing_completion_does_not_download_or_create(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch.object(Path, 'home', return_value=home), patch.object(installer, 'download') as download:
                with self.assertRaises(OSError): installer.main()
                download.assert_not_called()
                self.assertFalse((home/'pearlhash-dev-v0.0.34').exists())

    def test_verified_install_runtime_and_exit_propagation(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            home = Path(temporary)
            library = home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
            library.parent.mkdir(parents=True); library.write_bytes(b'synthetic library')
            for version in ('33', '31', '27', '17'):
                folder = home/('pearlhash-dev-v0.0.'+version); folder.mkdir()
                manifest = {'files': []}
                if version == '31':
                    manifest['required_cpu_library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
                raw = json.dumps(manifest).encode()
                (folder/'download-manifest.json').write_bytes(raw)
                stack.enter_context(patch.object(installer, 'V'+version, hashlib.sha256(raw).hexdigest()))
            (home/'pearlhash-dev-v0.0.33/cooperative-gpu-result.json').write_text(json.dumps({
                'complete': True, 'gpu_checked': True, 'submitted_shares': 0,
                'component_timing': {'same_input_transcripts_match': True}}))
            stack.enter_context(patch.object(Path, 'home', return_value=home))
            source = (ROOT/'tools/profile_dispatch.py').read_bytes()
            download = stack.enter_context(patch.object(installer, 'download', return_value=source))
            run = stack.enter_context(patch.object(installer.subprocess, 'run', return_value=SimpleNamespace(returncode=7)))
            self.assertEqual(installer.main(), 7)
            download.assert_called_once_with('pearlhash/tools/profile_dispatch.py')
            args = run.call_args.args[0]; env = run.call_args.kwargs['env']
            self.assertTrue(args[2].endswith('tools/profile_dispatch.py'))
            self.assertTrue(args[4].endswith('v0.0.33-sm120.ptx'))
            self.assertEqual(env['PYTHONPATH'], ':'.join(str(home/('pearlhash-dev-v0.0.'+v)) for v in ('34','33','27','17')))
            self.assertEqual(env['PEARL_HASH_LIBRARY'], str(library))
            self.assertEqual((home/'pearlhash-dev-v0.0.34/tools/profile_dispatch.py').read_bytes(), source)
            with self.assertRaisesRegex(ValueError, 'already exists'): installer.main()


if __name__ == '__main__': unittest.main()
