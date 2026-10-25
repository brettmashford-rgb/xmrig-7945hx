"""Pinned installer: missing dependencies and failed proof gate never connect. ISC."""
from contextlib import contextmanager,ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v036 as installer

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    @contextmanager
    def installed(self,preflight_status=0,valid=True):
        with tempfile.TemporaryDirectory()as temporary,ExitStack()as stack:
            home=Path(temporary)
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
            library.parent.mkdir(parents=True);library.write_bytes(b'synthetic library')
            for version in ('35','33','31','27','17'):
                folder=home/('pearlhash-dev-v0.0.'+version);folder.mkdir()
                manifest={'files':[]}
                if version=='31':manifest['required_cpu_library_sha256']=hashlib.sha256(library.read_bytes()).hexdigest()
                raw=json.dumps(manifest).encode();(folder/'download-manifest.json').write_bytes(raw)
                stack.enter_context(patch.object(installer,'V'+version,hashlib.sha256(raw).hexdigest()))
            (home/'pearlhash-dev-v0.0.35/prepared-gpu-result.json').write_text(json.dumps({
                'complete':True,'submitted_shares':0,'correctness':[{'passed':True}]*18,
                'changing':{label+'_'+mode:[{}]*8 for label in ('virtual','fragment','cooperative')for mode in ('original','prepared')}}))
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle'
            oracle.parent.mkdir(parents=True);oracle.write_text('synthetic verifier');oracle.chmod(0o700)
            login=home/'pearlhash-dev/captures/independent-login-test.json';login.parent.mkdir(parents=True)
            login.write_text(json.dumps({'schema':'pearlhash-login-probe-1','records':[{'direction':'out',
                'json':{'method':'login','params':['synthetic-wallet','test-worker','test-agent']}}]}))
            stack.enter_context(patch.object(Path,'home',return_value=home))
            download=stack.enter_context(patch.object(installer,'download',side_effect=lambda name:(ROOT.parent/name).read_bytes()))
            def fake_run(args,env):
                if args[2].endswith('check_prepared_job.py'):
                    if preflight_status:return SimpleNamespace(returncode=preflight_status)
                    output=Path(args[args.index('--output-dir')+1]);output.mkdir()
                    (output/'manifest.json').write_text(json.dumps({'complete':valid,'gpu_checked':True,
                        'official_cpu_verifier':'passed','submitted_shares':0,'pool_connection':False,
                        'stale_search_rejected':True,'stale_proof_rejected':True}))
                    return SimpleNamespace(returncode=0)
                return SimpleNamespace(returncode=7)
            run=stack.enter_context(patch.object(installer.subprocess,'run',side_effect=fake_run))
            yield home,run,download

    def test_missing_completion_never_downloads_or_starts(self):
        with tempfile.TemporaryDirectory()as temporary:
            home=Path(temporary)
            with patch.object(Path,'home',return_value=home),patch.object(installer,'download')as download:
                with self.assertRaises(OSError):installer.main()
                download.assert_not_called();self.assertFalse((home/'pearlhash-dev-v0.0.36').exists())

    def test_failed_offline_process_or_report_cannot_start_live_runner(self):
        with self.installed(preflight_status=3)as(home,run,download):
            self.assertEqual(installer.main(),3);self.assertEqual(run.call_count,1)
        with self.installed(valid=False)as(home,run,download):
            with self.assertRaisesRegex(ValueError,'live connection not started'):installer.main()
            self.assertEqual(run.call_count,1)

    def test_success_gates_exact_endpoint_runtime_and_live_exit(self):
        with self.installed()as(home,run,download):
            self.assertEqual(installer.main(),7);self.assertEqual(run.call_count,2)
            self.assertEqual(download.call_count,15)
            offline=run.call_args_list[0].args[0];live=run.call_args_list[1].args[0]
            env=run.call_args_list[1].kwargs['env']
            self.assertTrue(offline[2].endswith('tools/check_prepared_job.py'))
            self.assertTrue(live[2].endswith('tools/mine_bounded.py'))
            self.assertEqual(live[live.index('--host')+1],'pool.pearlhash.xyz')
            self.assertEqual(live[live.index('--port')+1],'9000')
            self.assertEqual(live[live.index('--seconds')+1],'300')
            self.assertNotIn('--observe-target',live)
            self.assertEqual(env['PYTHONPATH'],':'.join(str(home/('pearlhash-dev-v0.0.'+v))for v in ('36','35','33','27','17')))
            self.assertEqual(env['PEARL_HASH_LIBRARY'],str(home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'))
            with self.assertRaisesRegex(ValueError,'already exists'):installer.main()


if __name__=='__main__':unittest.main()
