"""Completed lean-direct proof/performance required before bounded live run. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v051 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.50';(previous/'offline-preflight').mkdir(parents=True)
            completed={'complete':True,'error':None,'pool_connection':False,'submitted_shares':0,
                'readback_contract_checked':True,'loop_comparison':{
                    'rounds':24,'unique_timed_tiles_per_mode':1572864,'preferred':'lean-v050',
                    'descriptor_path':'stream-reset-uniform-target-v050','speedup_over_v049':{'lean-v050':1.22698}},
                'driver_diagnostic':{'tiles_per_mode':65536,'separate_from_primary_timings':True,'modes':{}}}
            for label in ('packed-direct-v049','stream-reset-v050','lean-v050'):
                baseline=label=='packed-direct-v049'
                completed['driver_diagnostic']['modes'][label]={
                    'calls':{'cuMemcpyDtoH_v2':16,'cuLaunchKernel':32,'cuStreamSynchronize':16,
                        'cuMemcpyHtoD_v2':16 if baseline else 0,'cuCtxSynchronize':16 if baseline else 0,
                        'cuMemsetD32Async':0 if baseline else 16},
                    'copy_bytes':{'cuMemcpyDtoH_v2':8064,'cuMemcpyHtoD_v2':128 if baseline else 0}}
            if mode=='sparse-zeros':
                for data in completed['driver_diagnostic']['modes'].values():
                    for key in ('calls','copy_bytes'):data[key]={k:v for k,v in data[key].items()if v}
            preflight=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,official_cpu_verifiers=2,
                modes_checked=2,guard_cases=56,target_cases=36,transcript_windows=8,cpu_samples=16,
                partial_queue_checked=True,retained_windows_and_stale_rejected=True)
            if mode=='failed-proof':preflight['official_cpu_verifiers']=1
            if mode=='no-win':completed['loop_comparison']['speedup_over_v049']['lean-v050']=1.01
            if mode=='nan-win':completed['loop_comparison']['speedup_over_v049']['lean-v050']=float('nan')
            if mode=='infinite-win':completed['loop_comparison']['speedup_over_v049']['lean-v050']=float('inf')
            if mode=='wrong-winner':completed['loop_comparison']['preferred']='packed-resident-v048'
            if mode=='missing-stale':preflight.pop('retained_windows_and_stale_rejected')
            if mode=='missing-guard':preflight['guard_cases']=55
            if mode=='missing-driver':completed['readback_contract_checked']=False
            if mode=='bad-driver':completed['driver_diagnostic']['modes']['lean-v050']['calls']['cuMemcpyDtoH_v2']=400
            if mode=='bad-bytes':completed['driver_diagnostic']['modes']['lean-v050']['copy_bytes']['cuMemcpyHtoD_v2']=129
            if mode=='bad-reset':completed['driver_diagnostic']['modes']['lean-v050']['calls']['cuMemsetD32Async']=0
            if mode=='bad-context':completed['driver_diagnostic']['modes']['lean-v050']['calls']['cuCtxSynchronize']=1
            (previous/'lean-comparison.json').write_text(json.dumps(completed))
            (previous/'offline-preflight/manifest.json').write_text(json.dumps(preflight))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# test runner\n';package=json.dumps({'files':[{'path':'tools/mine_bounded.py',
                'repository_path':'pearlhash/tools/mine_bounded.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            stack.enter_context(patch.object(installer,'find_login',return_value=home/'local-login'))
            run=stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0)))
            if mode not in ('ok','sparse-zeros'):
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();run.assert_not_called()
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,19);self.assertEqual(run.call_count,1)
                args=run.call_args.args[0]
                for flag in ('--cache-a','--lean-direct','--commitment-module'):self.assertIn(flag,args)
                self.assertNotIn('--packed-direct',args);self.assertNotIn('--resident-maps',args);self.assertNotIn('--two-streams',args);self.assertNotIn('--oracle',args)
                self.assertEqual(args[args.index('--seconds')+1],'300')
                self.assertEqual(args[args.index('--host')+1],'pool.pearlhash.xyz')
                self.assertEqual(args[args.index('--module')+1],str(home/'pearlhash-dev-v0.0.48/releases/pearlhash-dev-v0.0.48-scan-sm120.ptx'))
                self.assertEqual(run.call_args.kwargs['env']['PYTHONPATH'].split(':')[0],str(home/'pearlhash-dev-v0.0.51'))
    def test_single_bounded_lean_direct_run_without_repeating_gpu_tests(self):self.exercise('ok')
    def test_failed_proof_blocks_download_and_live_connection(self):self.exercise('failed-proof')
    def test_no_clear_timing_win_blocks_live_connection(self):self.exercise('no-win')
    def test_nan_timing_cannot_enable_live_connection(self):self.exercise('nan-win')
    def test_infinite_timing_cannot_enable_live_connection(self):self.exercise('infinite-win')
    def test_other_winner_blocks_live_connection(self):self.exercise('wrong-winner')
    def test_missing_guard_blocks_live_connection(self):self.exercise('missing-guard')
    def test_missing_driver_gate_blocks_live_connection(self):self.exercise('missing-driver')
    def test_wrong_driver_counts_block_live_connection(self):self.exercise('bad-driver')
    def test_wrong_upload_bytes_block_live_connection(self):self.exercise('bad-bytes')
    def test_missing_reset_blocks_live_connection(self):self.exercise('bad-reset')
    def test_context_wait_regression_blocks_live_connection(self):self.exercise('bad-context')
    def test_real_report_omits_zero_call_fields(self):self.exercise('sparse-zeros')
    def test_missing_stale_gate_blocks_live_connection(self):self.exercise('missing-stale')


if __name__=='__main__':unittest.main()
