#!/usr/bin/env python3
"""Retry V85 Nsight counters with the small private CLI extraction; preserve baseline."""
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

SOURCE='77d2fd9d807c17a6e052f3ea540270d991690ce2'
MANIFEST_SHA='3223c43c25dc62a3da4caf0614733dace345e6082679d88d320a85f6668179ce'
HOME=Path.home()
RESULTS=HOME/'pearlhash-dev-v0.0.85'
STAGE=HOME/'pearlhash-dev-v0.0.85.1'
RAW='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/'+SOURCE+'/'
HELPER_SHA='c9774491fdc822ce8601ebc45e70ff69795ced260b44783c506dbaf3a745e6ad'
PTX=HOME/'pearlhash-dev-v0.0.80/releases/pearlhash-dev-v0.0.80-scan-sm120.ptx'
COMMITMENT=HOME/'pearlhash-dev-v0.0.39/releases/pearlhash-dev-v0.0.39-merkle-sm120.ptx'
PTX_SHA='99f53e9f0ae22496b8bf8348b24448060d50cc5d4440ee41a4d2ac04923bf0bf'
VERSIONS=(83,82,81,80,79,78,77,76,75,74,71,70,68,66,65,64,62,61,60,59,58,57,56,55,54,53,52,51,50,49,48,47,46,45,44,43,42,41,40,39,38,36,35,33,31,27,17)


def main():
    if not RESULTS.is_dir():raise ValueError('V85 baseline folder missing; run V85 first')
    if STAGE.exists():raise ValueError('V85.1 retry was already started; send counter-retry-result.json')
    baseline=json.loads((RESULTS/'baseline.json').read_text())
    suite=json.loads((RESULTS/'suite-result.json').read_text())
    if baseline.get('complete') is not True or baseline.get('error') is not None:
        raise ValueError('saved unprofiled V85 baseline did not complete')
    if suite.get('baseline_completed') is not True or suite.get('preferred')!='pair-direct' or suite.get('pool_connection') is not False:
        raise ValueError('saved V85 suite does not match the offline pair-direct baseline')
    if hashlib.sha256(PTX.read_bytes()).hexdigest()!=PTX_SHA:raise ValueError('winning PTX checksum differs')
    if not COMMITMENT.is_file():raise ValueError('installed commitment PTX missing')
    library=HOME/'pearlhash-dev-v0.0.16/bin/libpearlhash.so'
    if not library.is_file():raise ValueError('installed CPU library missing')
    deps=[HOME/('pearlhash-dev-v0.0.'+str(version)) for version in VERSIONS]
    deps.insert(0,HOME/'pearlhash-dev-v0.0.84.1')
    missing=[str(path) for path in [*deps,library,COMMITMENT] if not path.exists()]
    if missing:raise ValueError('V85 dependencies missing: '+', '.join(missing[:5]))
    with urllib.request.urlopen(RAW+'pearlhash/releases/pearlhash-dev-v0.0.85.1-files.json',timeout=60) as response:
        manifest=response.read(1024*1024)
    if hashlib.sha256(manifest).hexdigest()!=MANIFEST_SHA:raise ValueError('V85.1 retry manifest checksum mismatch')
    parsed=json.loads(manifest)
    entry=next((row for row in parsed['files'] if row.get('path')=='tools/ncu_profile.py'),None)
    if entry is None or entry.get('sha256')!=HELPER_SHA:raise ValueError('V85.1 helper manifest entry differs')
    with urllib.request.urlopen(RAW+entry['repository_path'],timeout=60) as response:raw=response.read(1024*1024)
    if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=HELPER_SHA:raise ValueError('V85.1 profiler helper checksum mismatch')
    STAGE.mkdir(mode=0o700)
    tools=STAGE/'tools';tools.mkdir(mode=0o700)
    (tools/'ncu_profile.py').write_bytes(raw)
    sys.path.insert(0,str(tools))
    from ncu_profile import prepare,collect
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(map(str,(RESULTS,*deps)))
    env['PEARL_HASH_LIBRARY']=str(library);env['PYTHONUNBUFFERED']='1'
    print('V85 saved baseline retained:',json.dumps(dict(
        tiles_s=baseline['baseline']['median_tiles_s'],
        full_nonce_tiles_s=baseline.get('board_energy',{}).get('tiles_per_second'),
        watts=baseline.get('board_energy',{}).get('average_power_w'),
        tiles_J=baseline.get('board_energy',{}).get('tiles_per_joule'))),flush=True)
    binary,source=prepare(RESULTS)
    print('Profiler source:',source,flush=True)
    report=collect(RESULTS,binary,env,PTX,COMMITMENT);report['source']=source
    (RESULTS/'hardware-counters-retry.json').write_text(json.dumps(report,indent=2)+'\n')
    result=dict(complete=report['available'],hardware_counters_available=report['available'],
        error=report['error'],baseline_reused=True,preferred='pair-direct',speed_promotion=False,
        pool_connection=False,submitted_shares=0)
    (STAGE/'counter-retry-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('HARDWARE COUNTERS:',json.dumps(report['compact'] if report['available'] else dict(available=False,error=report['error'])),flush=True)
    print('PREFERRED: pair-direct; V85 baseline retained; diagnostic only.',flush=True)
    print('COUNTER RETRY:',json.dumps(result),flush=True)
    print('Send HARDWARE COUNTERS and COUNTER RETRY.',flush=True)
    return 0 if report['available'] else 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('STOP:',error,flush=True);raise SystemExit(1)
