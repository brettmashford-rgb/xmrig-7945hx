#!/usr/bin/env python3
"""Install offline two-stream comparison using existing validated GPU kernel. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request
COMMIT='d2c7eaba5590a0e3f43896bd94471ca2e85a306d'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='9782b6a21de0b9f6bba7a73ab6e7fd999651ccfeffb4492490f6b3f80aa0be1e'
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
    home=Path.home();folder=home/'pearlhash-dev-v0.0.41'
    if folder.exists():raise ValueError('v0.0.41 directory already exists; send this output')
    versions=((40,V40),(39,V39),(38,V38),(36,V36),(35,V35),(33,V33),(31,V31),(27,V27),(17,V17))
    dependencies=[];cpu_manifest=None
    for version,pin in versions:
        dependency=home/('pearlhash-dev-v0.0.'+str(version))
        manifest=verify_package(dependency,pin);dependencies.append(dependency)
        if version==31:cpu_manifest=manifest
    previous=dependencies[0]
    preflight=json.loads((previous/'offline-preflight/manifest.json').read_text())
    completed=json.loads((previous/'mining-result.json').read_text())
    if (preflight.get('complete')is not True or preflight.get('error')is not None
            or preflight.get('official_cpu_verifier')!='passed'
            or preflight.get('scan_comparison',{}).get('preferred')!='cached-a'
            or completed.get('complete')is not True or completed.get('error')is not None
            or completed.get('worker',{}).get('joined')is not True
            or completed.get('scan_backend')!='cached-a-virtual-b-v040'):
        raise ValueError('v040 cached-A GPU/proof/live completion differs')
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    checked(library.read_bytes(),cpu_manifest['required_cpu_library_sha256'])
    print('v040 completion and installed source/PTX/library verified. No old proof tests repeated.',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.41-files.json'),MANIFEST)
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
    print('Checking two independent stream queues, then comparing identical windows. Offline only; no pool or shares.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/check_streams.py'),
        '--module',str(previous/'releases/pearlhash-dev-v0.0.40-scan-sm120.ptx'),
        '--report',str(folder/'stream-comparison.json')],env=env)
    print('Send STREAM COMPARISON and final output. Existing live miner configuration is unchanged.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
