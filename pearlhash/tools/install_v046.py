#!/usr/bin/env python3
"""Install bounded live resident-map worker using completed v045 validation. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request
COMMIT='045facaaaaddabcd5cd1473507957263a5994949'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='482400889d990fd9500713eb1d1cfa1b2fc2b87b02559e43a4a2242750a6b9ac'
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
    home=Path.home();folder=home/'pearlhash-dev-v0.0.46'
    if folder.exists():raise ValueError('v0.0.46 directory already exists; send this output')
    versions=((45,V45),(44,V44),(43,V43),(42,V42),(41,V41),(40,V40),(39,V39),(38,V38),(36,V36),(35,V35),(33,V33),(31,V31),(27,V27),(17,V17))
    dependencies=[];cpu_manifest=None
    for version,pin in versions:
        dependency=home/('pearlhash-dev-v0.0.'+str(version))
        manifest=verify_package(dependency,pin);dependencies.append(dependency)
        if version==31:cpu_manifest=manifest
    previous=dependencies[0]
    completed=json.loads((previous/'resident-comparison.json').read_text())
    preflight=json.loads((previous/'offline-preflight/manifest.json').read_text())
    comparison=completed.get('loop_comparison',{})
    if (completed.get('complete')is not True or completed.get('error')is not None
            or completed.get('pool_connection')is not False or completed.get('submitted_shares')!=0
            or comparison.get('rounds')!=20 or comparison.get('unique_timed_tiles_per_mode')!=1310720
            or comparison.get('preferred')!='resident-one-stream'
            or comparison.get('descriptor_path')!='resident-maps-gpu-built-v045'
            or comparison.get('speedup_resident_over_baseline',0)<=1/.97
            or preflight.get('complete')is not True or preflight.get('error')is not None
            or preflight.get('pool_connection')is not False or preflight.get('submitted_shares')!=0
            or preflight.get('official_cpu_verifier')!='passed' or preflight.get('target_cases')!=18
            or preflight.get('descriptor_windows')!=4 or preflight.get('cpu_samples')!=8
            or preflight.get('partial_queue_checked')is not True
            or preflight.get('retained_windows_and_stale_rejected')is not True):
        raise ValueError('v045 resident correctness/proof/performance completion differs; no live connection')
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    checked(library.read_bytes(),cpu_manifest['required_cpu_library_sha256'])
    print('Completed v045 resident GPU/proof/performance and source/PTX/library verified; no tests repeated.',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.46-files.json'),MANIFEST)
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
    module=previous/'releases/pearlhash-dev-v0.0.45-scan-sm120.ptx'
    commitment=home/'pearlhash-dev-v0.0.39/releases/pearlhash-dev-v0.0.39-merkle-sm120.ptx'
    login=find_login(home)
    print('Starting one five-minute live connection: resident maps, one stream, 4096-tile windows.',flush=True)
    print('Actual pool target; at most one fresh share. No reconnect or share retry.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/mine_bounded.py'),
        '--host','pool.pearlhash.xyz','--port','9000','--login-file',str(login),
        '--module',str(module),'--commitment-module',str(commitment),'--cache-a','--resident-maps',
        '--seconds','300','--report',str(folder/'mining-result.json')],env=env)
    print('Send final search summary, stage totals, resident descriptor windows and connection summary.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
