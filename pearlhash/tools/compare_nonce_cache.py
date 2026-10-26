#!/usr/bin/env python3
"""Paired production nonce preparation timings; unchanged v60 search is not timed. ISC."""
import argparse
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import time
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_search_loops import production_session
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from pool.search import prepare_nonce

MODES=('full-tree-v060','frontier-v061')
ROUNDS=20


def summary(samples,cache_setup):
    if set(samples)!=set(MODES)or any(len(samples[m])!=ROUNDS for m in MODES):raise ValueError('twenty paired nonce samples required')
    if (type(cache_setup)not in(int,float)or not 0<=cache_setup<float('inf')
            or any(type(v)not in(int,float)or not 0<v<float('inf')for values in samples.values()for v in values)):
        raise ValueError('invalid nonce timing sample')
    medians={m:statistics.median(samples[m])for m in MODES}
    totals={MODES[0]:sum(samples[MODES[0]]),MODES[1]:cache_setup+sum(samples[MODES[1]])}
    return dict(rounds=ROUNDS,median_seconds=medians,cache_build_seconds=cache_setup,
        speedup_nonce_preparation=medians[MODES[0]]/medians[MODES[1]],
        total_seconds_including_cache_build=totals,
        speedup_including_cache_build=totals[MODES[0]]/totals[MODES[1]],
        preferred=MODES[1]if totals[MODES[1]]<.97*totals[MODES[0]]else MODES[0],
        scope='nonce preparation only; not GPU search throughput or whole-miner speedup')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commitment-module',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,contexts_identical=0,
        gpu_scanner_unchanged='shared-B-v060',scope='actual production nonce preparation; no pool or GPU search timing')
    session=None
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        started=time.perf_counter();cache=NonceCommitmentCache.build(job,session.is_current);setup=time.perf_counter()-started
        worker=b'TESTWORK';miner=secrets.token_bytes(8)
        old=prepare_nonce(job,base,worker,miner,session.is_current)
        new=prepare_cached_nonce(job,base,worker,miner,session.is_current,cache)
        if old!=new:raise RuntimeError('warmup nonce contexts differ')
        samples={m:[]for m in MODES}
        for index in range(ROUNDS):
            miner=secrets.token_bytes(8);contexts={};order=MODES if index%2==0 else MODES[::-1]
            for mode in order:
                started=time.perf_counter()
                contexts[mode]=(prepare_nonce(job,base,worker,miner,session.is_current)if mode==MODES[0]else
                    prepare_cached_nonce(job,base,worker,miner,session.is_current,cache))
                samples[mode].append(time.perf_counter()-started)
            if contexts[MODES[0]]!=contexts[MODES[1]]:raise RuntimeError('timed nonce contexts differ')
            report['contexts_identical']+=1
            print('Nonce comparison round',str(index+1)+'/20 complete.',flush=True)
        report['nonce_comparison']=summary(samples,setup);report['wall_samples_seconds']=samples
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('NONCE COMPARISON:',json.dumps(report['nonce_comparison']),flush=True)
    print('Matched all 20 complete nonce contexts. GPU scanner unchanged; no pool connection or shares.',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
