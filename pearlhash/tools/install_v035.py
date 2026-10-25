#!/usr/bin/env python3
"""Install reusable-dispatch offline checks using verified local PTX. ISC."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import urllib.request

COMMIT = '6ea62f0a8346f32bdfdfb3a11ae6777d2c8a3947'
BASE = 'https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+COMMIT+'/'
MANIFEST = '9d508500da4f0de808d236db14afda684159cd2d32dff95401415bf8510caf78'
PROFILER = 'f8b511a60c5f3895bdd7ee873a440cd0e250cc368840c5e416dd5279c7fa6cd3'
V33 = '095c40640498ab466f2dfbdddeeda98527277450994f5d6140e219b091b2b2eb'
V31 = 'd5b60f745f1673b575e910a687a2c81e5144c4b1b62f9c91924410982e4206c8'
V27 = '92754526e52f4e12162fc86205cbdb5e1ef390558e3ef50b4957caa5efa6e8e7'
V17 = '2ab175ecf311bb7ab7aa35fbe31fbae547740dac8b6069602957cd8c2b10a183'


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
    home = Path.home(); folder = home/'pearlhash-dev-v0.0.35'
    previous = home/'pearlhash-dev-v0.0.34'; source = home/'pearlhash-dev-v0.0.33'
    runtime = home/'pearlhash-dev-v0.0.27'; reference = home/'pearlhash-dev-v0.0.17'
    library = home/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    if folder.exists(): raise ValueError('v0.0.35 directory already exists; send this output')
    completion = json.loads((previous/'dispatch-profile-result.json').read_text())
    if (completion.get('complete') is not True or completion.get('error') is not None
            or completion.get('submitted_shares') != 0 or completion.get('transcripts_match') is not True
            or any(len(completion.get('rounds', {}).get(label, [])) != 8
                   for label in ('virtual', 'fragment', 'cooperative'))):
        raise ValueError('previous dispatch profiling completion differs')
    checked((previous/'tools/profile_dispatch.py').read_bytes(), PROFILER)
    verify_package(source, V33)
    old = verify_package(home/'pearlhash-dev-v0.0.31', V31)
    verify_package(runtime, V27); verify_package(reference, V17)
    checked(library.read_bytes(), old['required_cpu_library_sha256'])
    print('Previous profiling completion, sources, PTX and local CPU library verified.', flush=True)
    raw = checked(download('pearlhash/releases/pearlhash-dev-v0.0.35-files.json'), MANIFEST)
    manifest = json.loads(raw); files = []
    for entry in manifest['files']:
        path = relative(entry['path'])
        if entry['repository_path'] != 'pearlhash/'+path.as_posix(): raise ValueError('source path differs')
        content = checked(download(entry['repository_path']), entry['sha256'])
        if len(content) != entry['bytes']: raise ValueError('source size differs')
        files.append((path, content))
    folder.mkdir(mode=0o700)
    for path, content in files:
        target = folder/path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    (folder/'download-manifest.json').write_bytes(raw)
    print('All four source checksums: OK. Existing GPU module reused.', flush=True)
    print('Checking reusable dispatches, repeated scans and 8192 distinct window queries.', flush=True)
    print('Offline synthetic inputs only; no pool connection, proof rebuild or shares.', flush=True)
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(map(str, (folder, previous, source, runtime, reference)))
    env['PEARL_HASH_LIBRARY'] = str(library); env['PYTHONUNBUFFERED'] = '1'
    result = subprocess.run([sys.executable, '-S', str(folder/'tools/check_prepared_gpu.py'),
        '--module', str(source/'releases/pearlhash-dev-v0.0.33-sm120.ptx'),
        '--report', str(folder/'prepared-gpu-result.json')], env=env)
    print('Send the final output, including REPEATED and CHANGING lines.', flush=True)
    return result.returncode


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('STOP:', error, flush=True); raise SystemExit(1)
