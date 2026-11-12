#!/usr/bin/env python3
"""Verify existing controls, prove independent experiments, then compare each target. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request
COMMIT='360ccc95f966962863ba91241361eb46675d75d2'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='08c62e1cf47caf5c00d61b40f9934b51d126d46db048b45089a1739ac697e756'
V83='91ae63b9662e879ac1b21b43a2345dd6a677e853ebaaf4f1cf66bb40c98aede6'
V82='c25b0064eddf6d84544f2b00d0cd7ba0e59e2d79b82732f2ca5b0bb0a6d107fe'
V81='afff0bb0abdc02f90b9220fb07b0e1b9666bb1d0a103bd69f73d44cb98603660'
V80='062103540a7e48fb40ff2f4a9e5a4d705e28706a96d7875c5e17997982dcbeb7'
V79='2f078f17778ddfac6d5e769bf5de2af8a50b1ddb7d45c9576a5dc579ff51ebb7'
V78='9fe67aa8fdc13cc1f3ec97c845c5d89cd33e7a9d516c60df9f5ebd8c1604529f'
V77='b449b913871cbe883efd32e49cefa362bee7373cf7c989d62e4f26e53ad972e8'
V76='555e5e6d1343cac36f410dfa664ca6fcad619d4db2f158d846e851320c74a76e'
V75='195672f575b3e0ccf9049e5610385cfb618a7933c972b5b4057feeb870ff4210'
V74='a84c3559ed055b5c4b88848edea35668cda8e05d7d1526463eb18f9b4fa92776'
V71='3d4da7a05bc04a4c032d6cabbcbd3fb59b2c5231e2f693b50648fafe8e6b6754'
V70='917b15ea4e82e19b8425b21bf9ed73558f8c07736b2a5cd740c0b28b02f1bd19'
V68='1238b4ca2e8a985ab0ef21d71bb1ea12fe538b9f619c625c297b3eca93121457'
V66='ed20f83ae2a141a935de2ea4273505553233fe2c7851cc6a214431ddaad403ec'
V65='c7113b94276854c7fc13498190601764d0743a76f2c9529905af1ebbd7d4f662'
V64='dcdaca6b68f0af2690d9fc605192cc0a43f353c184bf2324cbc85952d592c615'
V62='4e7bbb5347851e1d02fb3aa89aef0a7ef22dc96917c41262db1db4af211d5140'
V61='535d6569370a1016af0f365980bf1d1ab8e3ea707a70c508d0fd77abe90311bc'
V60='187d3f0f603b03572b61b1a8a6e99fc65d4f01064d8904697e0d270a47bd29af'
V59='a16862b27e7d2dc5266777de50eb4f8031e9d628e58bda912a8a3ed19ff983d6'
V58='c36cf207012797640911050a084465962ff880ea902b149f17fdafc31b3449ad'
V57='25f9c74d146abd677e90f4cf0978dea064c5a75245b50ce55cc504751f1b47bd'
V56='9e3edbe0d60a73aef9bbfaeb450e2a34dd3cb4240112e2684a670fee955c70db'
V55='a3ffa4dfb3abecae066a11b41cd4b1f61b285990e640d3a8ef6fc1eefb665d84'
V54='67916444df77a42f07573c303479578b523091fb5d32b4e30636004c95bb9eaf'
V53='086212c6e0149a82baac6a0d43a1be43c6eefbcac3ad7a5c3a8ad15439c12429'
V52='42331f0a60fa2a6ec10fa3c4bb73374b2be7491e770b1c4f6592725ed9a22954'
V51='072dde02516de0c74d1134909367e8b9752f10ee85d2d8fef9d83ddb24e40239'
V50='a21c9a4eb3bc9337d0844f65b642a7caf8178506b48b684c7615f75273d51315'
V49='4cfefa38de53e352d259c380c7092dcb5c73c65653e216bc451a6436b9df6423'
V48='74c99c7012d7cb762bb0d08d12cec05ddf6e89e303b7e41060d60699e83263e9'
V47='780e2f3864edcbfcf4f37e51e1853c8515ed5dfe4c84e54db650bbe7cd7cd40f'
V46='482400889d990fd9500713eb1d1cfa1b2fc2b87b02559e43a4a2242750a6b9ac'
V45='a03daa3ccd5923b7db92e9a14bd23369e41acf3cd03412aed746647fca319c54'
V44='a6b92bde0ee9b22c2b2fb130a30ee53bb0789298e16d4bca4bd149d697de6c1f'
V43='ba2930e7aa22d39d1fecad7030ad500fe7ce09f3597e39de984cbd29bf333d5f'
V42='f4674b4924a76b728e2cfc52e9da1c33fe6f9770ba86919a2b3f4b71c84db4b9'
V41='9782b6a21de0b9f6bba7a73ab6e7fd999651ccfeffb4492490f6b3f80aa0be1e'
V40='764604deee445878248e69eebcf82962c3effe04f8b694efcda89272d7338e1d'
V39='c84a4b9d80a656cdf08a6ffcd4005375b96cb2d611c580bbbde5403fa19f18b8'
V38='d53583c5dc3d3061b0bdf27a7fe25ac9e24cbe45eacd0d0ec105cd6f7605dc6f'
V36='9926da20eef7c258b6220e2720cdb8d9e2e1538c110fe2dbd78982699220097f'
V35='9d508500da4f0de808d236db14afda684159cd2d32dff95401415bf8510caf78'
V33='095c40640498ab466f2dfbdddeeda98527277450994f5d6140e219b091b2b2eb'
V31='d5b60f745f1673b575e910a687a2c81e5144c4b1b62f9c91924410982e4206c8'
V27='92754526e52f4e12162fc86205cbdb5e1ef390558e3ef50b4957caa5efa6e8e7'
V17='2ab175ecf311bb7ab7aa35fbe31fbae547740dac8b6069602957cd8c2b10a183'


def checked(raw,expected):
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('checksum differs; nothing started')
    return raw


def relative(name):
    path=PurePosixPath(name)
    if path.is_absolute()or not path.parts or any(x in('.','..')for x in path.parts):
        raise ValueError('unsafe package path')
    return Path(*path.parts)


def verify_package(folder,expected):
    manifest=json.loads(checked((folder/'download-manifest.json').read_bytes(),expected))
    for entry in manifest['files']:
        raw=(folder/relative(entry['path'])).read_bytes()
        if len(raw)!=entry['bytes']:raise ValueError('installed package size differs')
        checked(raw,entry['sha256'])
    return manifest


def download(path):
    request=urllib.request.Request(BASE+path,headers={'User-Agent':'PearlHash-source-installer'})
    with urllib.request.urlopen(request,timeout=60)as response:raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('source download exceeds cap')
    return raw



def require_fields(report,fields,label):
    if type(report)is not dict or any(key not in report or type(report[key])is not type(value)or report[key]!=value
            for key,value in fields.items()):raise ValueError(label+' completion differs')


def require_v75(folder):
    require_fields(json.loads((folder/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['wide16k','small4-wide16k','small4-schedule4-wide16k'],
        comparisons_completed=['combo'],pool_connection=False,submitted_shares=0),'v075 suite')
    report=json.loads((folder/'combo-comparison.json').read_text())
    require_fields(report,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='combo',canonical_work_sets_checked=True,readback_contract_checked=True,
        power_monitoring_attempted=True),'v075 comparison')
    require_fields(report.get('comparison'),dict(preferred='wide16k',rounds=12,
        unique_timed_tiles_per_mode=6291456),'v075 winner')



def show_summary(report):
    c=report['comparison']
    print('COMPACT V84 RESULTS (offline):',flush=True)
    for mode in ('pair-direct','projected-sparse'):
        power=report['power'].get('summary',{}).get(mode,{})
        full=report['power']['full_nonce_summary'][mode];resource=report['kernel_resources'][mode]
        print(json.dumps(dict(mode=mode,tiles_s=c['median_tiles_per_second'][mode],speedup=c['speedup_over_pair_direct'][mode],
            full_nonce_tiles_s=full['tiles_s'],watts=power.get('average_power_w'),tiles_J=power.get('tiles_per_joule'),
            registers=resource.get('registers_per_thread'),local_bytes=resource.get('local_bytes_per_thread'),blocks_SM=resource.get('max_active_blocks_per_sm'))),flush=True)
    print('PREFERRED:',c['preferred'],'SCAN ONLY:',c['scan_only_preferred'],'FULL NONCE SPEEDUP:',c['full_nonce_speedup'],flush=True)
    print('JOB PROJECTION:',json.dumps(dict(extra_setup_s=c['extra_job_setup_seconds'],break_even_nonces=c['job_setup_break_even_nonces'],
        setup_seconds=report['job_setup_seconds'],projection_bytes=report['projection_allocation_bytes'])),flush=True)


def main():
    home=Path.home();folder=home/'pearlhash-dev-v0.0.84'
    if folder.exists():raise ValueError('v0.0.84 directory already exists; send this output')
    versions=((83,V83),(82,V82),(81,V81),(80,V80),(79,V79),(78,V78),(77,V77),(76,V76),(75,V75),(74,V74),(71,V71),(70,V70),(68,V68),(66,V66),(65,V65),(64,V64),(62,V62),(61,V61),(60,V60),(59,V59),(58,V58),(57,V57),(56,V56),(55,V55),(54,V54),(53,V53),(52,V52),(51,V51),(50,V50),(49,V49),(48,V48),(47,V47),(46,V46),(45,V45),(44,V44),(43,V43),(42,V42),(41,V41),(40,V40),(39,V39),(38,V38),(36,V36),(35,V35),(33,V33),(31,V31),(27,V27),(17,V17))
    dependencies=[];cpu_manifest=None
    for version,pin in versions:
        dependency=home/('pearlhash-dev-v0.0.'+str(version))
        manifest=verify_package(dependency,pin);dependencies.append(dependency)
        if version==31:cpu_manifest=manifest
    previous=home/'pearlhash-dev-v0.0.60';nonce_folder=home/'pearlhash-dev-v0.0.61'
    live_folder=home/'pearlhash-dev-v0.0.62'
    live=json.loads((live_folder/'mining-result.json').read_text())
    require_fields(live,dict(complete=True,error=None,scan_backend='shared-B-job-cache-one-stream-v062'),'v062 live')
    require_fields(live.get('worker'),dict(joined=True),'v062 joined worker')
    lifecycle=live.get('job_b_lifecycle')
    if type(lifecycle)is not list or not lifecycle or any(type(row)is not dict or row.get('closed')is not True for row in lifecycle):
        raise ValueError('v062 B ownership completion differs')
    old_geometry=json.loads((live_folder/'offline-preflight/manifest.json').read_text())
    require_fields(old_geometry,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        production_contexts_checked=4,proof_contexts_checked=2,official_cpu_verifiers=2,
        gpu_scanner='shared-B-v060',nonce_cache_reused=True,production_leaves=163872,
        production_parent_hashes=7,stale_preparation_rejected=True,retained_windows_and_stale_rejected=True,
        b_tables_reused=True,transcript_windows=4,cpu_samples=8,guard_cases=28,
        production_b_table_builds=1,production_b_table_leases=2),'v062 B correctness/proof')
    nonce_report=json.loads((nonce_folder/'nonce-comparison.json').read_text())
    require_fields(nonce_report,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        contexts_identical=20,gpu_scanner_unchanged='shared-B-v060'),'v061 nonce comparison')
    nonce_timing=nonce_report.get('nonce_comparison',{})
    require_fields(nonce_timing,dict(rounds=20,preferred='frontier-v061'),'v061 preferred nonce preparation')
    gain=nonce_timing.get('speedup_including_cache_build',0)
    if not(type(gain)in(int,float)and 1/.97<gain<float('inf')):raise ValueError('v061 timing completion differs')
    nonce_proof=json.loads((nonce_folder/'offline-preflight/manifest.json').read_text())
    require_fields(nonce_proof,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        production_contexts_checked=4,proof_contexts_checked=2,official_cpu_verifiers=2,
        gpu_scanner='shared-B-v060',nonce_cache_reused=True,production_leaves=163872,
        production_parent_hashes=7,stale_preparation_rejected=True,
        retained_windows_and_stale_rejected=True),'v061 nonce proof')
    baseline=json.loads((previous/'shared-B-comparison.json').read_text())
    require_fields(baseline,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        readback_contract_checked=True,canonical_work_sets_checked=True),'v060 benchmark')
    comparison=baseline.get('loop_comparison',{})
    require_fields(comparison,dict(rounds=24,unique_timed_tiles_per_mode=1572864,
        preferred='shared-B-v060',descriptor_path='shared-B-pair-v060'),'v060 preferred baseline')
    gain=comparison.get('speedup_over_v059',{}).get('shared-B-v060',0)
    if not(type(gain)in(int,float)and 1/.97<gain<float('inf')):raise ValueError('v060 timing completion differs')
    preflight=json.loads((previous/'offline-preflight/manifest.json').read_text())
    require_fields(preflight,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        modes_checked=2,mapping_tiles=8388608,coverage_bijection_checked=True,
        canonical_windows_checked=True,canonical_hit_checked=True,transcript_windows=8,
        cpu_samples=16,target_cases=36,guard_cases=56,partial_queue_checked=True,
        official_cpu_verifiers=2,retained_windows_and_stale_rejected=True),'v060 proof/mapping')
    packed_folder=home/'pearlhash-dev-v0.0.64';geometry_folder=home/'pearlhash-dev-v0.0.65'
    packed=json.loads((packed_folder/'four-tile-comparison.json').read_text())
    require_fields(packed,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        readback_contract_checked=True,canonical_work_sets_checked=True),'v064 benchmark')
    require_fields(packed.get('loop_comparison'),dict(rounds=24,unique_timed_tiles_per_mode=1572864,
        preferred='packed-four-v064',descriptor_path='four-tile-40-row-pack-v064'),'v064 preferred packing')
    gain=packed['loop_comparison'].get('speedup_over_v060',{}).get('packed-four-v064',0)
    if not(type(gain)in(int,float)and 1/.97<gain<float('inf')):raise ValueError('v064 timing completion differs')
    packed_proof=json.loads((packed_folder/'offline-preflight/manifest.json').read_text())
    require_fields(packed_proof,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        modes_checked=2,official_cpu_verifiers=2,mapping_tiles=8388608,coverage_bijection_checked=True,
        canonical_windows_checked=True,canonical_hit_checked=True,transcript_windows=8,cpu_samples=16,
        target_cases=36,guard_cases=56,partial_queue_checked=True,retained_windows_and_stale_rejected=True),'v064 proof/mapping')
    geometry=json.loads((geometry_folder/'geometry-comparison.json').read_text())
    require_fields(geometry,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        gpu_scanner='shared-B-v060',readback_contract_checked=True,map_upload_savings_checked=True,
        contexts_and_ranges_identical=True),'v065 geometry benchmark')
    require_fields(geometry.get('geometry_comparison'),dict(rounds=24,tiles_per_nonce_per_mode=65536,
        unique_timed_tiles_per_mode=1572864,preferred='cached-maps-v065'),'v065 preferred geometry')
    gain=geometry['geometry_comparison'].get('amortized_speedup_over_v062',{}).get('cached-maps-v065',0)
    if not(type(gain)in(int,float)and 1/.97<gain<float('inf')):raise ValueError('v065 timing completion differs')
    geometry_proof=json.loads((geometry_folder/'offline-preflight/manifest.json').read_text())
    require_fields(geometry_proof,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        gpu_scanner='shared-B-v060',modes_checked=2,production_nonces=2,transcript_windows=8,cpu_samples=16,
        target_cases=36,partial_queues_checked=2,guard_cases=56,official_cpu_verifiers=2,
        retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True),'v065 geometry proof')
    v66_folder=home/'pearlhash-dev-v0.0.66'
    v66=json.loads((v66_folder/'mining-result.json').read_text())
    require_fields(v66,dict(complete=True,error=None,scan_backend='packed-four-geometry-one-stream-v066'),'v066 live')
    require_fields(v66.get('worker'),dict(joined=True),'v066 joined worker')
    for key in ('job_b_lifecycle','geometry_lifecycle'):
        rows=v66.get(key)
        if type(rows)is not list or not rows or any(type(row)is not dict or row.get('closed')is not True for row in rows):
            raise ValueError('v066 ownership completion differs')
    proof66=json.loads((v66_folder/'offline-preflight/manifest.json').read_text())
    require_fields(proof66,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        gpu_scanner='packed-four-v064',modes_checked=1,production_nonces=2,transcript_windows=8,cpu_samples=16,
        target_cases=18,partial_queues_checked=1,guard_cases=28,official_cpu_verifiers=2,
        retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True,
        proof_geometry_reused=True),'v066 fresh proof')
    pointer_folder=home/'pearlhash-dev-v0.0.68'
    pointer=json.loads((pointer_folder/'hoisted-a-comparison.json').read_text())
    require_fields(pointer,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        readback_contract_checked=True,canonical_work_sets_checked=True),'v068 benchmark')
    require_fields(pointer.get('loop_comparison'),dict(rounds=24,unique_timed_tiles_per_mode=1572864,
        preferred='a-pointer-v068',descriptor_path='hoisted-a-v068'),'v068 preferred pointers')
    gain=pointer['loop_comparison'].get('speedup_over_v066',{}).get('a-pointer-v068',0)
    if not(type(gain)in(int,float)and 1/.97<gain<float('inf')):raise ValueError('v068 timing completion differs')
    proof68=json.loads((pointer_folder/'offline-preflight-a-pointer-v068/manifest.json').read_text())
    require_fields(proof68,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        gpu_scanner='a-pointer-v068',modes_checked=1,production_nonces=2,transcript_windows=8,cpu_samples=16,
        target_cases=18,partial_queues_checked=1,guard_cases=28,official_cpu_verifiers=2,
        retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True,
        proof_geometry_reused=True),'v068 fresh pointer proof')
    for version,filename,winner,rounds,work,descriptor,extra in (
        (70,'CTA-shared B-comparison.json','cta8-v070',12,6291456,'cta-b-v070',dict(mapping_tiles=8388608,canonical_windows_checked=True,cta_guard_cases=5)),
        (71,'partition fold-comparison.json','partition-v071',24,1572864,'partition-fold-v071',{})):
        source=home/('pearlhash-dev-v0.0.'+str(version))
        previous_report=json.loads((source/filename).read_text())
        require_fields(previous_report,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
            readback_contract_checked=True,canonical_work_sets_checked=True),'v'+str(version)+' winning comparison')
        timing=previous_report.get('loop_comparison')
        require_fields(timing,dict(rounds=rounds,unique_timed_tiles_per_mode=work,preferred=winner,descriptor_path=descriptor),'v'+str(version)+' winning comparison')
        gain=timing.get('speedup_over_v068',{}).get(winner,0)
        if not(type(gain)in(int,float)and 1/.97<gain<float('inf')):raise ValueError('v'+str(version)+' winning comparison completion differs')
        previous_proof=json.loads((source/('offline-preflight-'+winner)/'manifest.json').read_text())
        required=dict(complete=True,error=None,pool_connection=False,submitted_shares=0,gpu_scanner=winner,
            modes_checked=1,production_nonces=2,transcript_windows=8,cpu_samples=16,target_cases=18,
            partial_queues_checked=1,guard_cases=28,official_cpu_verifiers=2,retained_windows_and_stale_rejected=True,
            map_payload_checked=True,geometry_reused=True,proof_geometry_reused=True)
        required.update(extra)
        require_fields(previous_proof,required,'v'+str(version)+' winning proof')
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    checked(library.read_bytes(),cpu_manifest['required_cpu_library_sha256'])
    print('Validated v60 GPU/proof/mapping and installed source/PTX/library verified; old GPU tests reused.',flush=True)
    previous74=home/'pearlhash-dev-v0.0.74'
    require_fields(json.loads((previous74/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['control','small4','small8','pipeline','panel-control','panel','wide16k'],
        comparisons_completed=['blocks','pipeline','batching','panel'],pool_connection=False,submitted_shares=0),'v074 suite')
    for group,winner in (('blocks','small4'),('batching','wide16k')):
        prior=json.loads((previous74/(group+'-comparison.json')).read_text())
        require_fields(prior,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
            canonical_work_sets_checked=True,readback_contract_checked=True),'v074 winning comparison')
        if prior['comparison']['preferred']!=winner:raise ValueError('v074 winning mode differs')
        speed=prior['comparison']['speedup_over_control'][winner]
        if type(speed)not in(int,float)or not 1/.97<speed<100:raise ValueError('v074 winner lacks promotion margin')
    previous75=home/'pearlhash-dev-v0.0.75'
    require_v75(previous75)
    previous76=home/'pearlhash-dev-v0.0.76'
    require_fields(json.loads((previous76/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['wide16k','wide16k-schedule4','wide16k-schedule8'],comparisons_completed=['schedule'],
        pool_connection=False,submitted_shares=0),'v076 suite')
    prior76=json.loads((previous76/'schedule-comparison.json').read_text())
    require_fields(prior76,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='schedule',canonical_work_sets_checked=True,readback_contract_checked=True,power_monitoring_attempted=True),'v076 comparison')
    require_fields(prior76.get('comparison'),dict(preferred='wide16k',rounds=12,unique_timed_tiles_per_mode=6291456),'v076 winner')
    prior77=home/'pearlhash-dev-v0.0.77'
    require_fields(json.loads((prior77/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['wide16k','wide16k-resident3','wide16k-resident4'],comparisons_completed=['register'],
        pool_connection=False,submitted_shares=0),'v077 suite')
    prior_report=json.loads((prior77/'register-comparison.json').read_text())
    require_fields(prior_report,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='register',canonical_work_sets_checked=True,readback_contract_checked=True),'v077 comparison')
    live77=json.loads((prior77/'mining-result.json').read_text())
    require_fields(live77,dict(complete=True,error=None,scan_backend='register-16k-one-stream-v077'),'v077 live')
    require_fields(live77.get('worker'),dict(joined=True),'v077 joined worker')
    for key in ('job_b_lifecycle','geometry_lifecycle'):
        rows=live77.get(key)
        if type(rows)is not list or not rows or any(type(row)is not dict or row.get('closed')is not True for row in rows):raise ValueError('v077 live owners differ')
    prior78=home/'pearlhash-dev-v0.0.78'
    require_fields(json.loads((prior78/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['wide16k','block64-wide16k','wide32k','wide64k'],comparisons_completed=['throughput'],
        pool_connection=False,submitted_shares=0),'v078 suite')
    previous78=json.loads((prior78/'throughput-comparison.json').read_text())
    require_fields(previous78,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='throughput',canonical_work_sets_checked=True,readback_contract_checked=True),'v078 comparison')
    require_fields(previous78.get('comparison'),dict(independent_preferred={'blocks':'wide16k','batching':'wide16k'}),'v078 retained baseline')
    prior79=home/'pearlhash-dev-v0.0.79'
    require_fields(json.loads((prior79/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['wide16k','pair-direct','pair-shared-a'],comparisons_completed=['a-share'],
        pool_connection=False,submitted_shares=0),'v079 suite')
    winner79=json.loads((prior79/'a-share-comparison.json').read_text())
    require_fields(winner79,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='a-share',canonical_work_sets_checked=True,readback_contract_checked=True),'v079 comparison')
    require_fields(winner79.get('comparison'),dict(preferred='pair-direct',rounds=12,unique_timed_tiles_per_mode=6291456),'v079 winner')
    gain=winner79['comparison'].get('speedup_over_wide16k',{}).get('pair-direct',0)
    if type(gain)not in(int,float)or not 1/.97<gain<float('inf'):raise ValueError('v079 winner lacks promotion margin')
    prior80=home/'pearlhash-dev-v0.0.80'
    require_fields(json.loads((prior80/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['pair-direct','pair-step2','pair-step8'],comparisons_completed=['pair-depth'],
        pool_connection=False,submitted_shares=0),'v080 suite')
    live80=json.loads((prior80/'mining-result.json').read_text())
    require_fields(live80,dict(complete=True,error=None,scan_backend='paired-depth-16k-one-stream-v080',scan_mode='pair-direct'),'v080 live')
    require_fields(live80.get('worker'),dict(joined=True),'v080 joined worker')
    prior81=home/'pearlhash-dev-v0.0.81'
    require_fields(json.loads((prior81/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['pair-direct','layout-col4','layout-col8'],comparisons_completed=['layout-width'],
        pool_connection=False,submitted_shares=0),'v081 suite')
    report81=json.loads((prior81/'layout-width-comparison.json').read_text())
    require_fields(report81,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='layout-width',canonical_work_sets_checked=True,readback_contract_checked=True,power_monitoring_attempted=True),'v081 comparison')
    require_fields(report81.get('comparison'),dict(preferred='pair-direct',rounds=12,unique_timed_tiles_per_mode=6291456),'v081 retained control')
    prior82=home/'pearlhash-dev-v0.0.82'
    require_fields(json.loads((prior82/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['pair-direct','twin-private-b','twin-shared-b'],comparisons_completed=['twin-b'],
        pool_connection=False,submitted_shares=0),'v082 suite')
    report82=json.loads((prior82/'twin-b-comparison.json').read_text())
    require_fields(report82,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
        experiment='twin-b',canonical_work_sets_checked=True,independent_nonce_bindings_checked=True,readback_contract_checked=True,power_monitoring_attempted=True),'v082 comparison')
    require_fields(report82.get('comparison'),dict(preferred='pair-direct',rounds=12,nonces_per_trial=2,unique_timed_tiles_per_mode=12582912,matched_private_is_diagnostic_only=True),'v082 retained control')
    prior83=home/'pearlhash-dev-v0.0.83'
    require_fields(json.loads((prior83/'suite-result.json').read_text()),dict(complete=True,failed={},
        preflights_passed=['pair-direct','native-direct','native-graph'],comparisons_completed=['dispatch'],pool_connection=False,submitted_shares=0),'v083 suite')
    r83=json.loads((prior83/'dispatch-comparison.json').read_text())
    require_fields(r83,dict(complete=True,error=None,experiment='dispatch',canonical_work_sets_checked=True,control_profile_completed=True,
        readback_contract_checked=True,power_monitoring_attempted=True,pool_connection=False,submitted_shares=0),'v083 comparison')
    require_fields(r83['comparison'],dict(preferred='pair-direct',rounds=12,unique_timed_tiles_per_mode=6291456),'v083 retained control')
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.84-files.json'),MANIFEST)
    package=json.loads(raw);files=[]
    for entry in package['files']:
        path=relative(entry['path'])
        if entry['repository_path']!='pearlhash/'+path.as_posix():raise ValueError('source path differs')
        content=checked(download(entry['repository_path']),entry['sha256'])
        if len(content)!=entry['bytes']:raise ValueError('source size differs')
        files.append((path,content))
    folder.mkdir(mode=0o700)
    for path,content in files:
        target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    (folder/'download-manifest.json').write_bytes(raw)
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(map(str,(folder,*dependencies)))
    env['PEARL_HASH_LIBRARY']=str(library);env['PYTHONUNBUFFERED']='1'
    module=folder/'releases/pearlhash-dev-v0.0.84-scan-sm120.ptx'
    commitment=home/'pearlhash-dev-v0.0.39/releases/pearlhash-dev-v0.0.39-merkle-sm120.ptx'
    oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle'
    if not os.access(oracle,os.X_OK):raise ValueError('existing official verifier required')
    modes=('pair-direct','projected-sparse')
    limits={mode:16384 for mode in modes}
    passed=[];failed={};completed=[]
    for mode in modes:
        output=folder/('offline-preflight-'+mode)
        print('Checking experiment',mode,'against v070 and independent CPU/proof references.',flush=True)
        result=subprocess.run([sys.executable,'-S',str(folder/'tools/check_projected.py'),
            '--mode',mode,'--module',str(module),'--commitment-module',str(commitment),'--oracle',str(oracle),'--output-dir',str(output)],env=env)
        if result.returncode:
            reason='preflight process failed (exit '+str(result.returncode)+')'
            try:
                details=json.loads((output/'manifest.json').read_text())
                if details.get('error'):reason=str(details['error'])
            except (OSError,ValueError,TypeError):pass
            failed[mode]=reason
            print('PREFLIGHT FAILED:',mode,reason,flush=True)
            continue
        try:
            checked_report=json.loads((output/'manifest.json').read_text())
            require_fields(checked_report,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                gpu_scanner=mode,modes_checked=1,production_nonces=2,transcript_windows=8,cpu_samples=16,
                target_cases=18,partial_queues_checked=1,guard_cases=38 if mode=='projected-sparse'else 28,official_cpu_verifiers=2,
                retained_windows_and_stale_rejected=True,map_payload_checked=True,geometry_reused=True,
                proof_geometry_reused=True,mapping_tiles=8388608,canonical_windows_checked=True,cta_guard_cases=5,
                large_queue_checked=True,large_queue_count=16384,odd_column_checked=True,odd_column_windows=6,odd_column_cpu_samples=2),'dispatch correctness/proof gate')
            if mode=='projected-sparse':require_fields(checked_report,dict(preparation_edges_checked=True,b_positive128_checked=True,tail_high_corrections_checked=True),'projection preparation edges')
            passed.append(mode)
        except (OSError,ValueError,KeyError,TypeError)as error:
            failed[mode]=str(error);print('STOP for',mode,':',error,flush=True)
    if len(passed)==len(modes):
        result=subprocess.run([sys.executable,'-S',str(folder/'tools/compare_projected.py'),
            '--module',str(module),'--commitment-module',str(commitment),'--report',str(folder/'projection-comparison.json')],env=env)
        if result.returncode:failed['projection-benchmark']='comparison process failed'
        else:
            try:
                report=json.loads((folder/'projection-comparison.json').read_text())
                require_fields(report,dict(complete=True,error=None,pool_connection=False,submitted_shares=0,
                    experiment='projection',canonical_work_sets_checked=True,readback_contract_checked=True,power_monitoring_attempted=True),'projection comparison')
                require_fields(report['power'],dict(attempted=True),'power monitoring')
                require_fields(report['comparison'],dict(rounds=12,unique_timed_tiles_per_mode=6291456),'v084 equal-work timing')
                if report['comparison'].get('preferred')not in modes:raise ValueError('invalid dispatch winner')
                require_fields(report['power']['full_nonce_summary']['pair-direct'],dict(tiles=50331648),'full nonce control credit')
                require_fields(report['power']['full_nonce_summary']['projected-sparse'],dict(tiles=50331648),'full nonce projected credit')
                completed.append('projection')
            except (OSError,ValueError,KeyError,TypeError)as error:failed['projection-benchmark']=str(error)
    else:failed['projection-benchmark']='required preflight failed'
    suite=dict(complete=not failed,failed=failed,preflights_passed=passed,comparisons_completed=completed,
        pool_connection=False,submitted_shares=0)
    (folder/'suite-result.json').write_text(json.dumps(suite,indent=2)+'\n')
    print('EXPERIMENT SUITE:',json.dumps(suite),flush=True)
    if completed:
        report=json.loads((folder/'projection-comparison.json').read_text())
        print('PROJECTION RESULT:',json.dumps({key:value for key,value in report['comparison'].items()if key!='wall_samples_seconds'}),flush=True)
        print('POWER RESULT:',json.dumps({key:value for key,value in report['power'].items()if key!='trials'}),flush=True)
        print('KERNEL RESOURCES:',json.dumps(report['kernel_resources']),flush=True)

    print('Send COMPACT V84 RESULTS, PREFERRED.',flush=True)
    if failed:return 1
    report=json.loads((folder/'projection-comparison.json').read_text())
    show_summary(report)
    print('Send COMPACT V84 RESULTS, PREFERRED.',flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
