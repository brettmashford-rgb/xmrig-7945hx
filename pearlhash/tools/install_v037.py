#!/usr/bin/env python3
"""Pinned live production diagnostic installer, no proof or shares. ISC."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import urllib.request

COMMIT='452761309ae30f54d2100d03d16822dce9a366ab'
BASE='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
SOURCE='15f05954e91259f55f0723357eba17b83d9d39a32cd784449b255b91693d0e6e'
V36='9926da20eef7c258b6220e2720cdb8d9e2e1538c110fe2dbd78982699220097f'
V35='9d508500da4f0de808d236db14afda684159cd2d32dff95401415bf8510caf78'
V33='095c40640498ab466f2dfbdddeeda98527277450994f5d6140e219b091b2b2eb'
V31='d5b60f745f1673b575e910a687a2c81e5144c4b1b62f9c91924410982e4206c8'
V27='92754526e52f4e12162fc86205cbdb5e1ef390558e3ef50b4957caa5efa6e8e7'
V17='2ab175ecf311bb7ab7aa35fbe31fbae547740dac8b6069602957cd8c2b10a183'
PROFILER='f8b511a60c5f3895bdd7ee873a440cd0e250cc368840c5e416dd5279c7fa6cd3'


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
    home=Path.home();folder=home/'pearlhash-dev-v0.0.37';previous=home/'pearlhash-dev-v0.0.36'
    if folder.exists():raise ValueError('v0.0.37 directory already exists; send this output')
    completion=json.loads((previous/'mining-result.json').read_text())
    preflight=json.loads((previous/'offline-preflight/manifest.json').read_text())
    if (completion.get('complete')is not True or completion.get('error')is not None
            or completion.get('worker',{}).get('joined')is not True
            or completion.get('scan_backend')!='prepared-production-virtual-v036'
            or preflight.get('complete')is not True or preflight.get('official_cpu_verifier')!='passed'):
        raise ValueError('previous live/preflight completion differs')
    for version,digest in (('36',V36),('35',V35),('33',V33),('27',V27),('17',V17)):
        verify_package(home/('pearlhash-dev-v0.0.'+version),digest)
    old=verify_package(home/'pearlhash-dev-v0.0.31',V31)
    library=home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    checked(library.read_bytes(),old['required_cpu_library_sha256'])
    checked((home/'pearlhash-dev-v0.0.34/tools/profile_dispatch.py').read_bytes(),PROFILER)
    login=find_login(home)
    print('Previous live completion and installed runtime verified. No proof tests repeated.',flush=True)
    source=checked(download('pearlhash/tools/profile_production.py'),SOURCE)
    folder.mkdir(mode=0o700);(folder/'tools').mkdir()
    script=folder/'tools/profile_production.py';script.write_bytes(source)
    env=os.environ.copy()
    env['PYTHONPATH']=os.pathsep.join(str(home/('pearlhash-dev-v0.0.'+version))
        for version in ('37','36','35','34','33','27','17'))
    env['PEARL_HASH_LIBRARY']=str(library);env['PYTHONUNBUFFERED']='1'
    print('One diagnostic pool connection, up to 90 seconds; no status reports, proof or submission.',flush=True)
    result=subprocess.run([sys.executable,'-S',str(script),'--login-file',str(login),
        '--module',str(home/'pearlhash-dev-v0.0.33/releases/pearlhash-dev-v0.0.33-sm120.ptx'),
        '--report',str(folder/'production-profile-result.json')],env=env)
    print('Send the final PLAIN WINDOWS, INSTRUMENTED WINDOWS, DISPATCH PROFILE and CPU FUNCTIONS output.',flush=True)
    return result.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError)as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
