"""Verified v60 baseline and fresh cached-nonce proof/equality gates precede timing. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v062 as installer


class Install(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            home=Path(temp);previous=home/'pearlhash-dev-v0.0.60';(previous/'offline-preflight').mkdir(parents=True)
            baseline=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                readback_contract_checked=True,canonical_work_sets_checked=True,loop_comparison=dict(
                    rounds=24,unique_timed_tiles_per_mode=1572864,preferred='shared-B-v060',
                    descriptor_path='shared-B-pair-v060',speedup_over_v059={'shared-B-v060':1.21449}))
            oldproof=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,modes_checked=2,
                mapping_tiles=8388608,coverage_bijection_checked=True,canonical_windows_checked=True,
                canonical_hit_checked=True,transcript_windows=8,cpu_samples=16,target_cases=36,
                guard_cases=56,partial_queue_checked=True,official_cpu_verifiers=2,retained_windows_and_stale_rejected=True)
            if mode=='wrong-winner':baseline['loop_comparison']['preferred']='order-only-v060'
            if mode=='no-margin':baseline['loop_comparison']['speedup_over_v059']['shared-B-v060']=1.01
            if mode=='missing-v60-proof':oldproof['official_cpu_verifiers']=1
            if mode=='missing-v60-mapping':oldproof['canonical_hit_checked']=False
            noncefolder=home/'pearlhash-dev-v0.0.61';(noncefolder/'offline-preflight').mkdir(parents=True)
            nonceproof=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                production_contexts_checked=4,proof_contexts_checked=2,official_cpu_verifiers=2,
                gpu_scanner='shared-B-v060',nonce_cache_reused=True,production_leaves=163872,
                production_parent_hashes=7,stale_preparation_rejected=True,retained_windows_and_stale_rejected=True)
            noncebench=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                contexts_identical=20,gpu_scanner_unchanged='shared-B-v060',nonce_comparison=dict(
                    rounds=20,preferred='frontier-v061',speedup_including_cache_build=19.58))
            if mode=='bad-v61-proof':nonceproof['official_cpu_verifiers']=1
            if mode=='bad-v61-benchmark':noncebench['contexts_identical']=19
            (noncefolder/'offline-preflight/manifest.json').write_text(json.dumps(nonceproof))
            (noncefolder/'nonce-comparison.json').write_text(json.dumps(noncebench))
            (previous/'shared-B-comparison.json').write_text(json.dumps(baseline))
            (previous/'offline-preflight/manifest.json').write_text(json.dumps(oldproof))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# source\n';package=json.dumps({'files':[{'path':'tools/check_nonce_cache_job.py',
                'repository_path':'pearlhash/tools/check_nonce_cache_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            stack.enter_context(patch.object(installer,'find_login',return_value=home/'private-login.json'))
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if len(calls)==1:self.assertNotIn('--host',args)
                if len(calls)==1:
                    if mode=='proof-process-failure':return SimpleNamespace(returncode=1)
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                        production_contexts_checked=4,proof_contexts_checked=2,official_cpu_verifiers=2,
                        gpu_scanner='shared-B-v060',nonce_cache_reused=True,production_leaves=163872,
                        production_parent_hashes=7,stale_preparation_rejected=True,retained_windows_and_stale_rejected=True,b_tables_reused=True,transcript_windows=4,cpu_samples=8,
                        guard_cases=28,production_b_table_builds=1,production_b_table_leases=2)
                    if mode=='missing-new-proof':report['official_cpu_verifiers']=1
                    if mode=='bad-context':report['production_contexts_checked']=3
                    if mode=='missing-reuse':report['nonce_cache_reused']=False
                    if mode=='missing-B':report['b_tables_reused']=False
                    if mode=='missing-guard':report['guard_cases']=27
                    if mode=='missing-transcript':report['transcript_windows']=3
                    if mode=='missing-stale':report['stale_preparation_rejected']=False
                    if mode=='different-gpu':report['gpu_scanner']='new-kernel'
                    if mode=='pool-connected':report['pool_connection']=True
                    output=Path(args[args.index('--output-dir')+1]);output.mkdir();(output/'manifest.json').write_text(json.dumps(report))
                else:
                    if mode=='timing-process-failure':return SimpleNamespace(returncode=1)
                    self.assertIn('--host',args);self.assertIn('--job-b-cache',args)
                    self.assertIn('--cache-a',args);self.assertEqual(args[args.index('--seconds')+1],'300')
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode in ('wrong-winner','no-margin','missing-v60-proof','missing-v60-mapping','bad-v61-proof','bad-v61-benchmark'):
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode in ('missing-new-proof','bad-context','missing-reuse','missing-stale','different-gpu','pool-connected','missing-B','missing-guard','missing-transcript'):
                with self.assertRaisesRegex(ValueError,'correctness/proof gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode in ('proof-process-failure','timing-process-failure'):
                self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1 if mode=='proof-process-failure'else 2)
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,30);self.assertEqual(len(calls),2)
                self.assertTrue(calls[0][2].endswith('check_job_b_cache.py'))
                self.assertTrue(calls[1][2].endswith('mine_bounded.py'))
                self.assertIn('--module',calls[1]);self.assertIn('--oracle',calls[0])
                self.assertEqual(calls[0][calls[0].index('--module')+1],str(previous/'releases/pearlhash-dev-v0.0.60-scan-sm120.ptx'))
    def test_proofs_then_nonce_comparison_with_unchanged_gpu_module(self):self.exercise('ok')
    def test_wrong_v60_winner_blocks_work(self):self.exercise('wrong-winner')
    def test_insufficient_v60_margin_blocks_work(self):self.exercise('no-margin')
    def test_old_proof_missing_blocks_work(self):self.exercise('missing-v60-proof')
    def test_old_mapping_missing_blocks_work(self):self.exercise('missing-v60-mapping')
    def test_new_proof_missing_blocks_timing(self):self.exercise('missing-new-proof')
    def test_context_mismatch_blocks_timing(self):self.exercise('bad-context')
    def test_missing_cache_reuse_blocks_timing(self):self.exercise('missing-reuse')
    def test_missing_stale_check_blocks_timing(self):self.exercise('missing-stale')
    def test_gpu_change_blocks_timing(self):self.exercise('different-gpu')
    def test_pool_connection_blocks_timing(self):self.exercise('pool-connected')
    def test_proof_process_failure_blocks_timing(self):self.exercise('proof-process-failure')
    def test_timing_process_failure_reported(self):self.exercise('timing-process-failure')
    def test_v61_proof_required(self):self.exercise('bad-v61-proof')
    def test_v61_benchmark_required(self):self.exercise('bad-v61-benchmark')
    def test_B_reuse_required_before_live_connection(self):self.exercise('missing-B')
    def test_all_guards_required_before_live_connection(self):self.exercise('missing-guard')
    def test_all_transcripts_required_before_live_connection(self):self.exercise('missing-transcript')


if __name__=='__main__':unittest.main()
