#!/usr/bin/env python3
"""Install early A/B alone, fresh proof gate and paired comparison against quad5. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request
COMMIT='1cebb37219f533fed188263e42c837ee28370538'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='9e3edbe0d60a73aef9bbfaeb450e2a34dd3cb4240112e2684a670fee955c70db'
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
    with urllib.request.urlopen(request,timeout=60)as response:raw=response.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('source download exceeds cap')
    return raw


def main():
    home=Path.home();folder=home/'pearlhash-dev-v0.0.56'
    if folder.exists():raise ValueError('v0.0.56 directory already exists; send this output')
    versions=((55,V55),(54,V54),(53,V53),(52,V52),(51,V51),(50,V50),(49,V49),(48,V48),(47,V47),(46,V46),(45,V45),(44,V44),(43,V43),(42,V42),(41,V41),(40,V40),(39,V39),(38,V38),(36,V36),(35,V35),(33,V33),(31,V31),(27,V27),(17,V17))
    dependencies=[];cpu_manifest=None
    for version,pin in versions:
        dependency=home/('pearlhash-dev-v0.0.'+str(version))
        manifest=verify_package(dependency,pin);dependencies.append(dependency)
        if version==31:cpu_manifest=manifest
    live=json.loads((home/'pearlhash-dev-v0.0.54/mining-result.json').read_text())
    if (live.get('complete')is not True or live.get('error')is not None
            or live.get('worker',{}).get('joined')is not True
            or live.get('scan_backend')!='quad5-one-stream-v054'):
        raise ValueError('v054 live completion differs; no GPU experiment started')
    previous_test=json.loads((home/'pearlhash-dev-v0.0.55/two-test-summary.json').read_text())
    if (previous_test.get('complete')is not True or previous_test.get('error')is not None
            or previous_test.get('pool_connection')is not False or previous_test.get('submitted_shares')!=0
            or set(previous_test.get('tests',{}))!={'test1','test2'}):
        raise ValueError('v055 offline completion differs; no GPU experiment started')
    previous=home/'pearlhash-dev-v0.0.52'
    completed=json.loads((previous/'b-quad-comparison.json').read_text())
    preflight=json.loads((previous/'offline-preflight/manifest.json').read_text())
    comparison=completed.get('loop_comparison',{})
    speedup=comparison.get('speedup_over_v051',{}).get('quad5-v052',0)
    if (completed.get('complete')is not True or completed.get('error')is not None
            or completed.get('pool_connection')is not False or completed.get('submitted_shares')!=0
            or completed.get('readback_contract_checked')is not True
            or comparison.get('rounds')!=24 or comparison.get('unique_timed_tiles_per_mode')!=1572864
            or comparison.get('preferred')!='quad5-v052' or comparison.get('descriptor_path')!='four-row-b-quad-v052'
            or not(type(speedup)in(int,float)and 1/.97<speedup<float('inf'))
            or preflight.get('complete')is not True or preflight.get('error')is not None
            or preflight.get('pool_connection')is not False or preflight.get('submitted_shares')!=0
            or preflight.get('modes_checked')!=2 or preflight.get('official_cpu_verifiers')!=2
            or preflight.get('transcript_windows')!=8 or preflight.get('cpu_samples')!=16
            or preflight.get('target_cases')!=36 or preflight.get('guard_cases')!=56
            or preflight.get('partial_queue_checked')is not True
            or preflight.get('retained_windows_and_stale_rejected')is not True):
        raise ValueError('v052 quad5 correctness/proof/performance completion differs')
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    checked(library.read_bytes(),cpu_manifest['required_cpu_library_sha256'])
    print('Completed v052 quad5 GPU/proof/performance and installed source/PTX/library verified; no old proof tests repeated.',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.56-files.json'),MANIFEST)
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
    module=folder/'releases/pearlhash-dev-v0.0.56-scan-sm120.ptx'
    commitment=home/'pearlhash-dev-v0.0.39/releases/pearlhash-dev-v0.0.39-merkle-sm120.ptx'
    oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle'
    if not os.access(oracle,os.X_OK):raise ValueError('existing official verifier required')
    output=folder/'offline-preflight'
    print('Checking early A/B alone against CPU/quad5 transcripts, queues, all guards and a fresh proof. Offline only.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/check_early_only_job.py'),
        '--module',str(module),'--commitment-module',str(commitment),'--oracle',str(oracle),'--output-dir',str(output)],env=env)
    if result.returncode:return result.returncode
    checked_report=json.loads((output/'manifest.json').read_text())
    if (checked_report.get('complete')is not True or checked_report.get('error')is not None
            or checked_report.get('pool_connection')is not False or checked_report.get('submitted_shares')!=0
            or checked_report.get('target_cases')!=18 or checked_report.get('transcript_windows')!=4
            or checked_report.get('cpu_samples')!=8 or checked_report.get('partial_queue_checked')is not True
            or checked_report.get('official_cpu_verifiers')!=1
            or checked_report.get('guard_cases')!=28 or checked_report.get('modes_checked')!=1
            or checked_report.get('retained_windows_and_stale_rejected')is not True):
        raise ValueError('Early-only correctness gate differs; comparison not started')
    print('Early-only correctness/proof gate passed. Comparing directly against quad5.',flush=True)
    report_path=folder/'early-only-comparison.json'
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/compare_early_only_loops.py'),
        '--module',str(module),'--commitment-module',str(commitment),'--variant','early-only',
        '--report',str(report_path)],env=env)
    if result.returncode:return result.returncode
    report=json.loads(report_path.read_text());comparison=report.get('loop_comparison',{})
    if (report.get('complete')is not True or report.get('error')is not None
            or report.get('pool_connection')is not False or report.get('submitted_shares')!=0
            or report.get('readback_contract_checked')is not True
            or comparison.get('rounds')!=24 or comparison.get('unique_timed_tiles_per_mode')!=1572864
            or comparison.get('descriptor_path')!='early-only-v056'):
        raise ValueError('early-only comparison completion differs')
    print('Send EARLY ONLY COMPARISON, DRIVER COUNTS and KERNEL RESOURCES. Offline only; live quad5 unchanged.',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
