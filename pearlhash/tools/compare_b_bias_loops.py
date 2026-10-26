#!/usr/bin/env python3
"""Biased B arithmetic versus validated v57 transpose on the same synthetic nonce. ISC."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import time
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.job import _HEADER_MASK,_SCRAMBLE_KEY
from pool.search import prepare_nonce
from pool.session import MiningProfile,PoolSession
from reference.patterns import PeriodicPattern
from tools.offline_nonce_search import make_job
from tools.gpu_base import prepare_gpu_base
from tools.production_scan import ProductionCandidateScanner
from tools.b_quad_scan import kernel_resources
from tools.b_bias_scan import new_bias_search

BASELINE='transpose-v057'
VARIANTS={'biased':'biased-v058'}
STEP={m:4096 for m in (BASELINE,*VARIANTS.values())}
WINDOW=65536
ROUNDS=24


def modes_for(variant):
    if type(variant)is not str or variant not in VARIANTS:raise ValueError('unknown loop variant')
    return BASELINE,VARIANTS[variant]


def production_session():
    profile=MiningProfile(5121,262144,32768,128,PeriodicPattern(bytes.fromhex('000103040000')),
                          PeriodicPattern(bytes.fromhex('000103010103')))
    session=PoolSession(profile,cert_version=3);header=make_job(secrets.token_bytes(32),3).header
    payload=bytes(value^_HEADER_MASK[i]^_SCRAMBLE_KEY[i%32]for i,value in enumerate(header))+bytes(124)
    session.consume({'id':0,'status':1,'result':True})
    session.consume({'id':-1,'status':1,'result':['extranonce',b'TESTWORK'.hex()]})
    job=session.consume({'id':-1,'status':1,'result':['notify',payload.hex(),(1).to_bytes(32,'little').hex(),bytes(8).hex(),'3']})
    return session,job


def run_window(search,mode,tiles=WINDOW):
    if mode not in STEP or type(tiles)is not int or tiles<1:raise ValueError('invalid loop comparison window')
    first=search.cursor.next_tile
    for offset in range(0,tiles,STEP[mode]):
        expected=first+min(offset+STEP[mode],tiles)
        hit,cursor=search.advance(min(STEP[mode],tiles-offset))
        if hit is not None or cursor.next_tile!=expected:
            raise RuntimeError('unexpected synthetic candidate or noncontiguous cursor')
    return first,search.cursor.next_tile


def summary(samples,setup,variant):
    modes=modes_for(variant)
    if set(samples)!=set(modes)or any(len(samples[m])!=ROUNDS for m in modes):
        raise ValueError('twenty-four paired samples per mode required')
    if any(type(v)not in(int,float)or not 0<v<float('inf') for values in samples.values()for v in values):
        raise ValueError('invalid loop timing sample')
    medians={m:statistics.median(samples[m])for m in modes}
    speedups={m:medians[modes[0]]/medians[m] for m in modes}
    fastest=min(modes,key=lambda m:medians[m])
    preferred=fastest if speedups[fastest]>1/.97 else modes[0]
    return {'rounds':ROUNDS,'tiles_per_round_per_mode':WINDOW,'unique_timed_tiles_per_mode':WINDOW*ROUNDS,
            'median_seconds':medians,'median_tiles_per_second':{m:WINDOW/medians[m]for m in modes},
            'speedup_over_v057':speedups,'preferred':preferred,'setup_seconds':setup,
            'timed_seconds_with_setup':{m:sum(samples[m])+setup[m]for m in modes},
            'wall_samples_seconds':samples}


class DriverCounts:
    """Separate diagnostic round; never wraps the twenty-four primary paired timing rounds."""
    def __init__(self,device):self.device=device;self.original=device.api;self.calls=Counter();self.bytes=Counter()
    def __enter__(self):
        def api(name,types,*args):
            self.calls[name]+=1
            if name in ('cuMemcpyDtoH_v2','cuMemcpyHtoD_v2'):self.bytes[name]+=int(args[2])
            return self.original(name,types,*args)
        self.device.api=api;return self
    def __exit__(self,*args):self.device.api=self.original
    def report(self):return {'calls':dict(self.calls),'copy_bytes':dict(self.bytes)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--commitment-module',type=Path,required=True)
    parser.add_argument('--variant',choices=tuple(VARIANTS),required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    modes=modes_for(args.variant);orders=(modes,modes[::-1])
    fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report={'complete':False,'error':None,'pool_connection':False,'submitted_shares':0,
        'scope':'same synthetic production job/nonce/target/ranges, v57 transpose versus biased B arithmetic, original 32-K loop; no pool, power or bandwidth saturation verdict',
        'includes':'planning within advance, upload, launch, waits, candidate queue reads, guards, generation checks and cursor handling',
        'excludes':'shared commitment/nonce preparation, initial CUDA context/JIT, pool receiving/status and proof building; search/cache setup reported separately'}
    session=device=None;searches={}
    try:
        session,job=production_session()
        print('Preparing one synthetic production job and nonce for both paths. No pool connection.',flush=True)
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        setup={}
        # Both caches remain resident in the same context throughout timed runs.
        # This avoids mode-dependent allocation/JIT and cache setup between rounds.
        for mode,variant in zip(modes,('transpose',args.variant)):
            started=time.perf_counter();searches[mode]=new_bias_search(context,device,session.is_current,biased=variant=='biased')
            setup[mode]=time.perf_counter()-started
        report['kernel_resources']={mode:kernel_resources(searches[mode].backend.dispatch)for mode in modes}
        for mode in modes:run_window(searches[mode],mode)
        samples={m:[]for m in modes};stages={m:[]for m in modes};ranges=[]
        for round_id in range(ROUNDS):
            order=orders[round_id%len(orders)];observed={}
            for mode in order:
                search=searches[mode];before=search.backend.stats();started=time.perf_counter()
                observed[mode]=run_window(search,mode);elapsed=time.perf_counter()-started
                after=search.backend.stats();samples[mode].append(elapsed)
                stages[mode].append({key:after[key]-before[key]for key in ('prepare_seconds','scan_seconds','dispatches','prepared_batches')})
            if len(set(observed.values()))!=1:raise RuntimeError('timed modes searched different global tile ranges')
            ranges.append(observed[modes[0]])
            print('Full-loop comparison round',str(round_id+1)+'/24 complete.',flush=True)
        counts={};diagnostic_ranges={}
        for mode in modes:
            with DriverCounts(device)as counter:diagnostic_ranges[mode]=run_window(searches[mode],mode)
            counts[mode]=counter.report()
        if len(set(diagnostic_ranges.values()))!=1:raise RuntimeError('diagnostic ranges differ')
        for mode in modes:
            calls=counts[mode]['calls'];copies=counts[mode]['copy_bytes']
            if (calls.get('cuMemcpyDtoH_v2',0)!=16 or copies.get('cuMemcpyDtoH_v2',0)!=8064
                    or calls.get('cuLaunchKernel',0)!=32 or calls.get('cuStreamSynchronize',0)!=16
                    or calls.get('cuMemcpyHtoD_v2',0)!=0
                    or copies.get('cuMemcpyHtoD_v2',0)!=0
                    or calls.get('cuCtxSynchronize',0)!=0
                    or calls.get('cuMemsetD32Async',0)!=16):
                raise RuntimeError('driver diagnostic contract differs: '+mode)
        report['readback_contract_checked']=True
        report['loop_comparison']=summary(samples,setup,args.variant);report['loop_comparison']['descriptor_path']='b-bias-v058';report['loop_comparison']['stage_samples']=stages
        report['loop_comparison']['timed_tile_ranges']=ranges
        report['driver_diagnostic']={'tiles_per_mode':WINDOW,'separate_from_primary_timings':True,'modes':counts}
        for search in searches.values():search.close()
        if device.allocations:raise RuntimeError('search comparison leaked device allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if session is not None:session.close()
        for resource in [*searches.values(),device]:
            if resource is not None:
                try:resource.close()
                except Exception as exc:report['error']=report['error']or('cleanup: '+str(exc))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    compact={key:value for key,value in report['loop_comparison'].items()if key not in ('wall_samples_seconds','stage_samples','timed_tile_ranges')}
    print('B BIAS COMPARISON:',json.dumps(compact),flush=True)
    print('DRIVER COUNTS:',json.dumps(report['driver_diagnostic']),flush=True)
    print('KERNEL RESOURCES:',json.dumps(report['kernel_resources']),flush=True)
    print('Comparison complete. No pool connection, shares, service or clock changes.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
