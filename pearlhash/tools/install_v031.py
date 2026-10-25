#!/usr/bin/env python3
"""Install pinned v31 source/PTX and check reusable GPU inputs offline. ISC.

Reuses verified local v17/v27 runtime and CPU library. No service/clock changes.
"""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request

COMMIT='b2a47492e0db3ca09d21fd1647e426213d035a78'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='d5b60f745f1673b575e910a687a2c81e5144c4b1b62f9c91924410982e4206c8'
V30='bd24ea83929f29cabad0a0332cde9802d0a9d4256ec99866d1db71b6587c4d8b'
V27='92754526e52f4e12162fc86205cbdb5e1ef390558e3ef50b4957caa5efa6e8e7'
V17='2ab175ecf311bb7ab7aa35fbe31fbae547740dac8b6069602957cd8c2b10a183'
LIBRARY='1b0127307179b124178bdbd50c86b587984b42cc04390cdc73bf8fcb8cf284a9'


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


def download(path):
    request=urllib.request.Request(BASE+path,headers={'User-Agent':'PearlHash-source-installer'})
    with urllib.request.urlopen(request,timeout=60)as response:raw=response.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('source download exceeds cap')
    return raw


def main():
    home=Path.home();folder=home/'pearlhash-dev-v0.0.31'
    previous_folder=home/'pearlhash-dev-v0.0.30'
    runtime=home/'pearlhash-dev-v0.0.27';reference=home/'pearlhash-dev-v0.0.17'
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    if folder.exists():raise ValueError('v0.0.31 directory already exists; send this output')
    previous=json.loads((previous_folder/'target-observation.json').read_text())
    if (previous.get('complete')is not True or previous.get('error')is not None
            or previous.get('worker',{}).get('joined')is not True or previous.get('submitted_shares')!=0):
        raise ValueError('previous live target observation differs')
    verify_package(previous_folder,V30);verify_package(runtime,V27);verify_package(reference,V17);checked(library.read_bytes(),LIBRARY)
    print('Previous target observation and installed runtime verified; old proof tests not repeated.',flush=True)
    print('Downloading v0.0.31 reusable-input GPU kernel and source...',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.31-files.json'),MANIFEST)
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
    print('All seventeen source/PTX checksums: OK.',flush=True)
    print('Checking the NEW cached-input GPU path, then comparing same-input component times. No pool connection.',flush=True)
    print('Existing WildRig/XMRig services and clocks remain unchanged.',flush=True)
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(map(str,(folder,runtime,reference)))
    env['PEARL_HASH_LIBRARY']=str(library);env['PYTHONUNBUFFERED']='1'
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/check_cached_gpu.py'),
        '--module',str(folder/'releases/pearlhash-dev-v0.0.31-sm120.ptx'),
        '--report',str(folder/'cache-gpu-result.json')],env=env)
    print('Send the final output. Completion report saved locally.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
