"""Verified v60 baseline and fresh cached-nonce proof/equality gates precede timing. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v072 as installer


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
            livefolder=home/'pearlhash-dev-v0.0.62';(livefolder/'offline-preflight').mkdir(parents=True)
            live=dict(complete=True,error=None,scan_backend='shared-B-job-cache-one-stream-v062',worker=dict(joined=True),job_b_lifecycle=[dict(closed=True)])
            bproof=dict(nonceproof,b_tables_reused=True,transcript_windows=4,cpu_samples=8,guard_cases=28,
                production_b_table_builds=1,production_b_table_leases=2)
            if mode=='bad-v62-live':live['complete']=False
            if mode=='unjoined-v62':live['worker']['joined']=False
            if mode=='bad-v62-owner':live['job_b_lifecycle'][0]['closed']=False
            if mode=='bad-v62-proof':bproof['guard_cases']=27
            (livefolder/'mining-result.json').write_text(json.dumps(live))
            (livefolder/'offline-preflight/manifest.json').write_text(json.dumps(bproof))
            packedfolder=home/'pearlhash-dev-v0.0.64';(packedfolder/'offline-preflight').mkdir(parents=True)
            packedreport=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                readback_contract_checked=True,canonical_work_sets_checked=True,loop_comparison=dict(
                    rounds=24,unique_timed_tiles_per_mode=1572864,preferred='packed-four-v064',
                    descriptor_path='four-tile-40-row-pack-v064',speedup_over_v060={'packed-four-v064':1.37058}))
            packedproof=dict(oldproof)
            geometryfolder=home/'pearlhash-dev-v0.0.65';(geometryfolder/'offline-preflight').mkdir(parents=True)
            geometryreport=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                gpu_scanner='shared-B-v060',readback_contract_checked=True,map_upload_savings_checked=True,
                contexts_and_ranges_identical=True,geometry_comparison=dict(rounds=24,tiles_per_nonce_per_mode=65536,
                    unique_timed_tiles_per_mode=1572864,preferred='cached-maps-v065',
                    amortized_speedup_over_v062={'cached-maps-v065':1.5}))
            geometryproof=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                gpu_scanner='shared-B-v060',modes_checked=2,production_nonces=2,transcript_windows=8,
                cpu_samples=16,target_cases=36,partial_queues_checked=2,guard_cases=56,official_cpu_verifiers=2,
                retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True)
            if mode=='bad-v64-winner':packedreport['loop_comparison']['preferred']='four-share-v064'
            if mode=='bad-v64-proof':packedproof['official_cpu_verifiers']=1
            if mode=='bad-v65-winner':geometryreport['geometry_comparison']['preferred']='cached-plan-v065'
            if mode=='bad-v65-proof':geometryproof['geometry_reused']=False
            (packedfolder/'four-tile-comparison.json').write_text(json.dumps(packedreport))
            (packedfolder/'offline-preflight/manifest.json').write_text(json.dumps(packedproof))
            (geometryfolder/'geometry-comparison.json').write_text(json.dumps(geometryreport))
            (geometryfolder/'offline-preflight/manifest.json').write_text(json.dumps(geometryproof))
            v66folder=home/'pearlhash-dev-v0.0.66';(v66folder/'offline-preflight').mkdir(parents=True)
            v66=dict(complete=True,error=None,scan_backend='packed-four-geometry-one-stream-v066',
                worker=dict(joined=True),job_b_lifecycle=[dict(closed=True)],geometry_lifecycle=[dict(closed=True)])
            if mode=='bad-v66-live':v66['complete']=False
            if mode=='bad-v66-owner':v66['geometry_lifecycle'][0]['closed']=False
            if mode=='bad-v66-worker':v66['worker']['joined']=False
            v66proof=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                gpu_scanner='packed-four-v064',modes_checked=1,production_nonces=2,transcript_windows=8,cpu_samples=16,
                target_cases=18,partial_queues_checked=1,guard_cases=28,official_cpu_verifiers=2,
                retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True,proof_geometry_reused=True)
            if mode=='bad-v66-proof':v66proof['official_cpu_verifiers']=1
            (v66folder/'mining-result.json').write_text(json.dumps(v66))
            (v66folder/'offline-preflight/manifest.json').write_text(json.dumps(v66proof))
            pointerfolder=home/'pearlhash-dev-v0.0.68';(pointerfolder/'offline-preflight-a-pointer-v068').mkdir(parents=True)
            pointerreport=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                readback_contract_checked=True,canonical_work_sets_checked=True,loop_comparison=dict(
                    rounds=24,unique_timed_tiles_per_mode=1572864,preferred='a-pointer-v068',
                    descriptor_path='hoisted-a-v068',speedup_over_v066={'a-pointer-v068':1.03904428}))
            pointerproof=dict(v66proof,gpu_scanner='a-pointer-v068')
            if mode=='bad-v68-winner':pointerreport['loop_comparison']['preferred']='packed-v066'
            if mode=='bad-v68-margin':pointerreport['loop_comparison']['speedup_over_v066']['a-pointer-v068']=1.01
            if mode=='bad-v68-proof':pointerproof['official_cpu_verifiers']=1
            (pointerfolder/'hoisted-a-comparison.json').write_text(json.dumps(pointerreport))
            (pointerfolder/'offline-preflight-a-pointer-v068/manifest.json').write_text(json.dumps(pointerproof))
            for version,winner,filename,rounds,work,descriptor in (
                (70,'cta8-v070','CTA-shared B-comparison.json',12,6291456,'cta-b-v070'),
                (71,'partition-v071','partition fold-comparison.json',24,1572864,'partition-fold-v071')):
                winnerfolder=home/('pearlhash-dev-v0.0.'+str(version))
                (winnerfolder/('offline-preflight-'+winner)).mkdir(parents=True)
                report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                    readback_contract_checked=True,canonical_work_sets_checked=True,
                    loop_comparison=dict(rounds=rounds,unique_timed_tiles_per_mode=work,preferred=winner,
                        descriptor_path=descriptor,speedup_over_v068={winner:1.08}))
                proof=dict(v66proof,gpu_scanner=winner)
                if version==70:proof.update(mapping_tiles=8388608,canonical_windows_checked=True,cta_guard_cases=5,winner_control_windows=8)
                if mode=='bad-v'+str(version)+'-winner':report['loop_comparison']['preferred']='wrong'
                if mode=='bad-v'+str(version)+'-margin':report['loop_comparison']['speedup_over_v068'][winner]=1.01
                if mode=='bad-v'+str(version)+'-proof':proof['official_cpu_verifiers']=1
                (winnerfolder/filename).write_text(json.dumps(report))
                (winnerfolder/('offline-preflight-'+winner)/'manifest.json').write_text(json.dumps(proof))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# source\n';package=json.dumps({'files':[{'path':'tools/check_nonce_cache_job.py',
                'repository_path':'pearlhash/tools/check_nonce_cache_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            # No local wallet/login lookup is used by the offline installer.
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                self.assertNotIn('--host',args);self.assertNotIn('--login-file',args)
                if len(calls)<=1:
                    if mode=='proof-process-failure':return SimpleNamespace(returncode=1)
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                        gpu_scanner=args[args.index('--mode')+1],modes_checked=1,production_nonces=2,transcript_windows=8,
                        cpu_samples=16,target_cases=18,partial_queues_checked=1,guard_cases=28,official_cpu_verifiers=2,
                        retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True,
                        proof_geometry_reused=True,mapping_tiles=8388608,canonical_windows_checked=True,cta_guard_cases=5,winner_control_windows=8)
                    if mode=='bad-cta-guard':report['cta_guard_cases']=4
                    if mode=='missing-winning-control':report['winner_control_windows']=7
                    if mode=='bad-new-mapping':report['canonical_windows_checked']=False
                    if mode=='missing-proof-reuse':report['proof_geometry_reused']=False
                    if mode=='missing-new-proof':report['official_cpu_verifiers']=0
                    if mode=='bad-context':report['target_cases']=17
                    if mode=='missing-reuse':report['geometry_reused']=False
                    if mode=='missing-B':report['map_payload_checked']=False
                    if mode=='missing-guard':report['guard_cases']=27
                    if mode=='missing-transcript':report['transcript_windows']=3
                    if mode=='missing-stale':report['retained_windows_and_stale_rejected']=False
                    if mode=='different-gpu':report['cpu_samples']=7
                    if mode=='pool-connected':report['pool_connection']=True
                    output=Path(args[args.index('--output-dir')+1]);output.mkdir();(output/'manifest.json').write_text(json.dumps(report))
                else:
                    if mode=='timing-process-failure':return SimpleNamespace(returncode=1)
                    self.assertTrue(args[2].endswith('compare_combined.py'))
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode in ('wrong-winner','no-margin','missing-v60-proof','missing-v60-mapping','bad-v61-proof','bad-v61-benchmark','bad-v62-live','unjoined-v62','bad-v62-owner','bad-v62-proof','bad-v64-winner','bad-v64-proof','bad-v65-winner','bad-v65-proof','bad-v66-live','bad-v66-owner','bad-v66-worker','bad-v66-proof','bad-v68-winner','bad-v68-margin','bad-v68-proof','bad-v70-winner','bad-v70-margin','bad-v70-proof','bad-v71-winner','bad-v71-margin','bad-v71-proof'):
                with self.assertRaisesRegex(ValueError,'completion differs'):installer.main()
                download.assert_not_called();self.assertEqual(calls,[])
            elif mode in ('missing-new-proof','bad-context','missing-reuse','missing-stale','different-gpu','pool-connected','missing-B','missing-guard','missing-transcript','missing-proof-reuse','bad-new-mapping','bad-cta-guard','missing-winning-control'):
                with self.assertRaisesRegex(ValueError,'correctness/proof gate'):installer.main()
                self.assertEqual(len(calls),1)
            elif mode in ('proof-process-failure','timing-process-failure'):
                self.assertEqual(installer.main(),1);self.assertEqual(len(calls),1 if mode=='proof-process-failure'else 2)
            else:
                self.assertEqual(installer.main(),0);self.assertEqual(verify.call_count,37);self.assertEqual(len(calls),2)
                self.assertTrue(calls[0][2].endswith('check_combined.py'))
                self.assertTrue(calls[1][2].endswith('compare_combined.py'))
                self.assertIn('--module',calls[1]);self.assertIn('--oracle',calls[0])
                self.assertEqual(calls[0][calls[0].index('--module')+1],str(home/'pearlhash-dev-v0.0.72/releases/pearlhash-dev-v0.0.72-scan-sm120.ptx'))
    def test_CTA_uniform_exit_guards_required(self):self.exercise('bad-cta-guard')
    def test_v70_winner_required(self):self.exercise('bad-v70-winner')
    def test_v70_margin_required(self):self.exercise('bad-v70-margin')
    def test_v70_proof_required(self):self.exercise('bad-v70-proof')
    def test_v71_winner_required(self):self.exercise('bad-v71-winner')
    def test_v71_margin_required(self):self.exercise('bad-v71-margin')
    def test_v71_proof_required(self):self.exercise('bad-v71-proof')
    def test_both_winning_kernel_comparisons_required(self):self.exercise('missing-winning-control')
    def test_v68_winner_required(self):self.exercise('bad-v68-winner')
    def test_v68_margin_required(self):self.exercise('bad-v68-margin')
    def test_v68_proof_required(self):self.exercise('bad-v68-proof')
    def test_new_canonical_mapping_required(self):self.exercise('bad-new-mapping')
    def test_v66_live_gate(self):self.exercise('bad-v66-live')
    def test_v66_owner_gate(self):self.exercise('bad-v66-owner')
    def test_v66_worker_gate(self):self.exercise('bad-v66-worker')
    def test_v66_proof_gate(self):self.exercise('bad-v66-proof')
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
    def test_fresh_proofs_must_reuse_geometry_before_live(self):self.exercise('missing-proof-reuse')
    def test_v64_packing_winner_required(self):self.exercise('bad-v64-winner')
    def test_v64_proof_required(self):self.exercise('bad-v64-proof')
    def test_v65_maps_winner_required(self):self.exercise('bad-v65-winner')
    def test_v65_reuse_proof_required(self):self.exercise('bad-v65-proof')
    def test_v62_live_required(self):self.exercise('bad-v62-live')
    def test_v62_worker_must_be_joined(self):self.exercise('unjoined-v62')
    def test_v62_owner_must_be_closed(self):self.exercise('bad-v62-owner')
    def test_v62_proof_required(self):self.exercise('bad-v62-proof')
    def test_v61_proof_required(self):self.exercise('bad-v61-proof')
    def test_v61_benchmark_required(self):self.exercise('bad-v61-benchmark')
    def test_B_reuse_required_before_live_connection(self):self.exercise('missing-B')
    def test_all_guards_required_before_live_connection(self):self.exercise('missing-guard')
    def test_all_transcripts_required_before_live_connection(self):self.exercise('missing-transcript')


if __name__=='__main__':unittest.main()
