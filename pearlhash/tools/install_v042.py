#!/usr/bin/env python3
"""Install bounded live two-stream experiment using existing validated GPU kernel. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request
COMMIT='abc5d69dad3f19342ccc3f05f4b730b346b4468b'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='f4674b4924a76b728e2cfc52e9da1c33fe6f9770ba86919a2b3f4b71c84db4b9'
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
    home=Path.home();folder=home/'pearlhash-dev-v0.0.42'
    if folder.exists():raise ValueError('v0.0.42 directory already exists; send this output')
    versions=((41,V41),(40,V40),(39,V39),(38,V38),(36,V36),(35,V35),(33,V33),(31,V31),(27,V27),(17,V17))
    dependencies=[];cpu_manifest=None
    for version,pin in versions:
        dependency=home/('pearlhash-dev-v0.0.'+str(version))
        manifest=verify_package(dependency,pin);dependencies.append(dependency)
        if version==31:cpu_manifest=manifest
    previous=dependencies[0];cached=dependencies[1];commitment=dependencies[2]
    completed=json.loads((previous/'stream-comparison.json').read_text())
    comparison=completed.get('stream_comparison',{})
    if (completed.get('complete')is not True or completed.get('error')is not None
            or completed.get('pool_connection')is not False or completed.get('submitted_shares')!=0
            or len(completed.get('cases',[]))!=15 or any(row.get('passed')is not True for row in completed.get('cases',[]))
            or comparison.get('rounds')!=20 or comparison.get('preferred')!='two-streams'
            or comparison.get('speedup',0)<=1/.97):
        raise ValueError('v041 validated stream comparison completion differs')
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    checked(library.read_bytes(),cpu_manifest['required_cpu_library_sha256'])
    oracle=home/'pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle'
    if not os.access(oracle,os.X_OK):raise ValueError('existing official verifier required')
    login=find_login(home)
    print('Previous stream correctness/performance and installed source/PTX/library verified.',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.42-files.json'),MANIFEST)
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
    module=cached/'releases/pearlhash-dev-v0.0.40-scan-sm120.ptx'
    commitment_module=commitment/'releases/pearlhash-dev-v0.0.39-merkle-sm120.ptx'
    output=folder/'offline-preflight'
    print('Checking new paired search, fresh V3 proof and in-flight replacement. No pool connection.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/check_dual_job.py'),
        '--module',str(module),'--commitment-module',str(commitment_module),
        '--oracle',str(oracle),'--output-dir',str(output)],env=env)
    if result.returncode:return result.returncode
    preflight=json.loads((output/'manifest.json').read_text())
    if (preflight.get('complete')is not True or preflight.get('error')is not None
            or preflight.get('official_cpu_verifier')!='passed' or preflight.get('pool_connection')is not False
            or preflight.get('submitted_shares')!=0
            or any(preflight.get(key)is not True for key in ('retained_two_windows','single_tail_passed',
                'inflight_stale_pair_rejected','stale_proof_rejected'))):
        raise ValueError('fresh paired proof/lifecycle gate differs; live connection not started')
    print('Offline paired proof gate passed. Starting one five-minute live connection, actual target, at most one share.',flush=True)
    print('Two cached-A streams; no reconnect or share retry. Existing services and clocks unchanged.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/mine_bounded.py'),
        '--host','pool.pearlhash.xyz','--port','9000','--login-file',str(login),
        '--module',str(module),'--commitment-module',str(commitment_module),'--cache-a','--two-streams',
        '--seconds','300','--report',str(folder/'mining-result.json')],env=env)
    print('Send final search summary, stage totals, reusable dispatch totals and connection summary.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
