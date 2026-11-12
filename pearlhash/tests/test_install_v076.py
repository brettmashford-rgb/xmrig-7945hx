"""Verified v60 baseline and fresh cached-nonce proof/equality gates precede timing. ISC."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v076 as installer


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
            prior74=home/'pearlhash-dev-v0.0.74';prior74.mkdir()
            suite74=dict(complete=True,failed={},preflights_passed=['control','small4','small8','pipeline','panel-control','panel','wide16k'],
                comparisons_completed=['blocks','pipeline','batching','panel'],pool_connection=False,submitted_shares=0)
            if mode=='bad-v74-suite':suite74['complete']=False
            (prior74/'suite-result.json').write_text(json.dumps(suite74))
            for group,winner in (('blocks','small4'),('batching','wide16k')):
                row=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,canonical_work_sets_checked=True,readback_contract_checked=True,
                    comparison=dict(preferred=winner,speedup_over_control={winner:1.1}))
                if mode=='bad-v74-winner':row['comparison']['preferred']='wrong'
                if mode=='bad-v74-margin':row['comparison']['speedup_over_control'][winner]=1.01
                (prior74/(group+'-comparison.json')).write_text(json.dumps(row))
            prior75=home/'pearlhash-dev-v0.0.75';prior75.mkdir()
            suite75=dict(complete=True,failed={},preflights_passed=['wide16k','small4-wide16k','small4-schedule4-wide16k'],
                comparisons_completed=['combo'],pool_connection=False,submitted_shares=0)
            report75=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,experiment='combo',
                canonical_work_sets_checked=True,readback_contract_checked=True,power_monitoring_attempted=True,
                comparison=dict(preferred='wide16k',rounds=12,unique_timed_tiles_per_mode=6291456))
            if mode=='bad-v75-suite':suite75['complete']=False
            if mode=='bad-v75-comparison':report75['readback_contract_checked']=False
            if mode=='bad-v75-winner':report75['comparison']['preferred']='small4-wide16k'
            (prior75/'suite-result.json').write_text(json.dumps(suite75))
            (prior75/'combo-comparison.json').write_text(json.dumps(report75))
            library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so';library.parent.mkdir(parents=True);library.write_bytes(b'test')
            oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle';oracle.parent.mkdir(parents=True);oracle.write_text('test');oracle.chmod(0o700)
            cpu={'required_cpu_library_sha256':hashlib.sha256(b'test').hexdigest()}
            source=b'# source\n';package=json.dumps({'files':[{'path':'tools/check_nonce_cache_job.py',
                'repository_path':'pearlhash/tools/check_nonce_cache_job.py','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]}).encode()
            stack.enter_context(patch.object(Path,'home',return_value=home))
            verify=stack.enter_context(patch.object(installer,'verify_package',return_value=cpu))
            stack.enter_context(patch.object(installer,'MANIFEST',hashlib.sha256(package).hexdigest()))
            download=stack.enter_context(patch.object(installer,'download',side_effect=[package,source]))
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if '--mode'in args:
                    selected=args[args.index('--mode')+1]
                    if mode=='process-failure'and selected=='wide16k-schedule4':return SimpleNamespace(returncode=1)
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                        gpu_scanner=selected,modes_checked=1,production_nonces=2,transcript_windows=8,cpu_samples=16,
                        target_cases=18,partial_queues_checked=1,guard_cases=28,official_cpu_verifiers=2,
                        retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True,proof_geometry_reused=True,
                        mapping_tiles=8388608,canonical_windows_checked=True,cta_guard_cases=5,large_queue_checked=True)
                    if mode=='bad-guard'and selected=='wide16k-schedule4':report['guard_cases']=26
                    if mode=='bad-large-queue'and selected=='wide16k-schedule8':report['large_queue_checked']=False
                    if mode=='bad-proof'and selected=='wide16k':report['official_cpu_verifiers']=1
                    folder=Path(args[args.index('--output-dir')+1]);folder.mkdir();(folder/'manifest.json').write_text(json.dumps(report))
                else:
                    if mode=='timing-failure':return SimpleNamespace(returncode=1)
                    report=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,experiment='schedule',
                        canonical_work_sets_checked=True,readback_contract_checked=True,power_monitoring_attempted=True,
                        comparison={},power=dict(attempted=True,available=False),kernel_resources={})
                    if mode=='bad-benchmark':report['readback_contract_checked']=False
                    if mode=='missing-monitoring':report['power_monitoring_attempted']=False
                    Path(args[args.index('--report')+1]).write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            stack.enter_context(patch.object(installer.subprocess,'run',side_effect=run))
            if mode.startswith('bad-v'):
                with self.assertRaises(ValueError):installer.main()
                download.assert_not_called();self.assertFalse(calls)
            else:
                result=installer.main();self.assertEqual(result,0 if mode=='ok'else 1)
                folder=home/'pearlhash-dev-v0.0.76';suite=json.loads((folder/'suite-result.json').read_text())
                self.assertEqual(sum('--mode'in row for row in calls),3)
                if mode=='ok':self.assertTrue(suite['complete']);self.assertEqual(len(calls),4);self.assertEqual(verify.call_count,39)
                else:self.assertFalse(suite['complete']);self.assertTrue(suite['failed'])
                if mode in ('bad-guard','bad-large-queue','bad-proof','process-failure'):self.assertEqual(len(calls),3)
    def test_all_three_preflights_and_combined_power_benchmark(self):self.exercise('ok')
    def test_bad_guards_block_timing(self):self.exercise('bad-guard')
    def test_large_queue_required_for_every_mode(self):self.exercise('bad-large-queue')
    def test_two_proofs_required(self):self.exercise('bad-proof')
    def test_failed_process_blocks_timing(self):self.exercise('process-failure')
    def test_comparison_failure_reported(self):self.exercise('timing-failure')
    def test_benchmark_gate_checked(self):self.exercise('bad-benchmark')
    def test_power_monitoring_cannot_be_omitted(self):self.exercise('missing-monitoring')
    def test_prior_winners_required(self):
        for mode in ('bad-v75-suite','bad-v75-comparison','bad-v75-winner','bad-v74-suite','bad-v74-winner','bad-v74-margin','bad-v70-winner','bad-v70-margin','bad-v70-proof','bad-v71-winner','bad-v71-margin','bad-v71-proof',
                'bad-v68-winner','bad-v68-margin','bad-v68-proof','bad-v66-live','bad-v66-proof'):self.exercise(mode)

if __name__=='__main__':unittest.main()
