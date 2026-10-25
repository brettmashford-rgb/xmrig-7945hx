#!/usr/bin/env python3
"""Install pinned v29 source and run one bounded live mining attempt. ISC.

Reuses verified local v17/v27 runtime and CPU library. No service/clock changes.
"""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request

COMMIT='122fdb37892875f3dcc111cd3b7a88e37aaa6dfb'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST='1372bea1c2dacc5a622afe5aecea08ab70c10b2186e399b93cf0f9665d81fe97'
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
    with urllib.request.urlopen(request,timeout=60)as response:raw=response.read(128*1024+1)
    if len(raw)>128*1024:raise ValueError('source download exceeds cap')
    return raw


def main():
    home=Path.home();folder=home/'pearlhash-dev-v0.0.29'
    runtime=home/'pearlhash-dev-v0.0.27';reference=home/'pearlhash-dev-v0.0.17'
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    if folder.exists():raise ValueError('v0.0.29 directory already exists; send this output')
    previous=json.loads((runtime/'live-search-result.json').read_text())
    if (previous.get('complete')is not True or previous.get('gpu_checked')is not True
            or previous.get('worker',{}).get('joined')is not True or previous.get('submitted_shares')!=0):
        raise ValueError('previous GPU completion record differs')
    verify_package(runtime,V27);verify_package(reference,V17);checked(library.read_bytes(),LIBRARY)
    print('Existing GPU completion and runtime verified; no old tests repeated.',flush=True)
    captures=home/'pearlhash-dev/captures'
    login=None
    for path in sorted(captures.glob('independent-login-*.json'),reverse=True):
        if not path.is_file()or path.stat().st_size>1024**2:continue
        try:
            data=json.loads(path.read_text())
            requests=[r['json']for r in data.get('records',[])if r.get('direction')=='out'
                      and r.get('json',{}).get('method')=='login']
            if (data.get('schema')=='pearlhash-login-probe-1'and data.get('error')is None
                    and len(requests)==1 and isinstance(requests[0].get('params'),list)
                    and len(requests[0]['params'])==3 and type(requests[0]['params'][0])is str):
                login=path;break
        except (ValueError,KeyError,TypeError):continue
    if login is None:raise ValueError('saved independent login not found; nothing started')
    print('Downloading v0.0.29 bounded live mining source...',flush=True)
    raw=checked(download('pearlhash/releases/pearlhash-dev-v0.0.29-files.json'),MANIFEST)
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
    print('All eleven source checksums: OK.',flush=True)
    print('Starting one live connection, up to five minutes, at most one fresh custom share.',flush=True)
    print('Existing WildRig/XMRig services and clocks remain unchanged.',flush=True)
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(map(str,(folder,runtime,reference)))
    env['PEARL_HASH_LIBRARY']=str(library);env['PYTHONUNBUFFERED']='1'
    result=subprocess.run([sys.executable,'-S',str(folder/'tools/mine_bounded.py'),
        '--host','pool.pearlhash.xyz','--port','9000','--login-file',str(login),
        '--module',str(runtime/'releases/pearlhash-dev-v0.0.27-sm120.ptx'),
        '--seconds','300','--report',str(folder/'mining-result.json')],env=env)
    print('Send the final output. Completion report saved locally.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
