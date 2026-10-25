#!/usr/bin/env python3
"""Install conditional cached-A scan experiment; offline fresh-proof gate before bounded pool run. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request

COMMIT='2c072626a1dc7ac38825ae3b3a05dd892ec05b5b'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='764604deee445878248e69eebcf82962c3effe04f8b694efcda89272d7338e1d'
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


def find_login(home):
    for path in sorted((home/'pearlhash-dev/captures').glob('independent-login-*.json'),reverse=True):
        if not path.is_file()or path.stat().st_size>1024**2:continue
        try:
            data=json.loads(path.read_text())
            requests=[r['json']for r in data.get('records',[])if r.get('direction')=='out'
                      and r.get('json',{}).get('method')=='login']
            if (data.get('schema')=='pearlhash-login-probe-1'and data.get('error')is None
                    and len(requests)==1 and isinstance(requests[0].get('params'),list)
                    and len(requests[0]['params'])==3 and type(requests[0]['params'][0])is str):
                return path
        except (ValueError,KeyError,TypeError):continue
    raise ValueError('saved independent login not found; nothing started')


def main():
    home=Path.home();folder=home/'pearlhash-dev-v0.0.40'
    previous=home/'pearlhash-dev-v0.0.36';source=home/'pearlhash-dev-v0.0.33'
    runtime=home/'pearlhash-dev-v0.0.27';reference=home/'pearlhash-dev-v0.0.17'
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle'
    if folder.exists():raise ValueError('v0.0.40 directory already exists; send this output')
    completed_folder=home/'pearlhash-dev-v0.0.39'
    completion=json.loads((completed_folder/'mining-result.json').read_text())
    preflight=json.loads((completed_folder/'offline-preflight/manifest.json').read_text())
    if (completion.get('complete')is not True or completion.get('error')is not None
            or completion.get('worker',{}).get('joined')is not True
            or completion.get('commitment_backend')!='gpu-constant-v039'
            or preflight.get('complete')is not True or preflight.get('official_cpu_verifier')!='passed'
            or preflight.get('production_root_match')is not True):
        raise ValueError('previous canonical-axis live/proof completion differs')
    verify_package(completed_folder,V39);verify_package(home/'pearlhash-dev-v0.0.38',V38)
    verify_package(previous,V36);verify_package(home/'pearlhash-dev-v0.0.35',V35);verify_package(source,V33)
    old=verify_package(home/'pearlhash-dev-v0.0.31',V31)
    verify_package(runtime,V27);verify_package(reference,V17)
    checked(library.read_bytes(),old['required_cpu_library_sha256'])
    if not oracle.is_file()or not os.access(oracle,os.X_OK):raise ValueError('existing official CPU verifier required')
    login=find_login(home)
    print('Previous GPU completion and installed source/PTX/library verified; wallet retained locally.',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.40-files.json'),MANIFEST)
    manifest=json.loads(raw);files=[]
    for entry in manifest['files']:
        path=relative(entry['path'])
        if entry['repository_path']!='pearlhash/'+path.as_posix():raise ValueError('source path differs')
        content=checked(download(entry['repository_path']),entry['sha256'])
        if len(content)!=entry['bytes']:raise ValueError('source size differs')
        files.append((path,content))
    folder.mkdir(mode=0o700)
    for path,content in files:
        target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    (folder/'download-manifest.json').write_bytes(raw)
    print('All ten source/PTX checksums: OK. New scan module installed; verified commitment module reused.',flush=True)
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(map(str,(folder,completed_folder,home/'pearlhash-dev-v0.0.38',previous,home/'pearlhash-dev-v0.0.35',source,runtime,reference)))
    env['PEARL_HASH_LIBRARY']=str(library);env['PYTHONUNBUFFERED']='1'
    module=folder/'releases/pearlhash-dev-v0.0.40-scan-sm120.ptx'
    commitment=completed_folder/'releases/pearlhash-dev-v0.0.39-merkle-sm120.ptx'
    output=folder/'offline-preflight'
    print('First: cached-A correctness, exact production-window timing and a fresh proof. No pool connection.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/check_cached_a.py'),
        '--module',str(module),'--commitment-module',str(commitment),'--oracle',str(oracle),'--output-dir',str(output)],env=env)
    if result.returncode:return result.returncode
    preflight=json.loads((output/'manifest.json').read_text())
    if (preflight.get('complete')is not True or preflight.get('gpu_checked')is not True
            or preflight.get('official_cpu_verifier')!='passed' or preflight.get('submitted_shares')!=0
            or preflight.get('pool_connection')is not False or preflight.get('error')is not None
            or len(preflight.get('cases',[]))!=18 or any(row.get('passed')is not True for row in preflight.get('cases',[]))
            or preflight.get('scan_comparison',{}).get('windows')!=16
            or preflight.get('scan_comparison',{}).get('queries_per_window')!=4096):
        raise ValueError('offline preflight report differs; live connection not started')
    choice=preflight.get('scan_comparison',{}).get('preferred')
    if choice=='baseline':
        print('Cached-A correctness passed, but it did not beat baseline including setup. Live experiment skipped.',flush=True)
        print('Send SCAN COMPARISON. The established v039 path remains recommended.',flush=True)
        return 0
    if choice!='cached-a':raise ValueError('unknown benchmark choice; live connection not started')
    print('Cached-A won the comparison. Starting one five-minute live connection; actual target, at most one fresh share.',flush=True)
    print('Receiver stays active; replaced jobs discard stale work. No automatic reconnect or share retry.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/mine_bounded.py'),
        '--host','pool.pearlhash.xyz','--port','9000','--login-file',str(login),
        '--module',str(module),'--commitment-module',str(commitment),'--cache-a','--seconds','300','--report',str(folder/'mining-result.json')],env=env)
    print('Send the final output, including SCAN COMPARISON, search summary, stage totals and connection summary.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
