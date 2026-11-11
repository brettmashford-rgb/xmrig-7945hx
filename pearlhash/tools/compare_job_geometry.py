#!/usr/bin/env python3
"""Three-way fresh-nonce lifecycle timing; unchanged v062 search kernel. ISC."""
import argparse
from itertools import permutations
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import time
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_search_loops import production_session,DriverCounts
from tools.production_scan import ProductionCandidateScanner
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.job_b_tables import JobBTables,new_job_b_search
from tools.job_geometry import JobGeometry,new_geometry_search

MODES=('fresh-v062','cached-plan-v065','cached-maps-v065')
ORDERS=tuple(permutations(MODES));ROUNDS=24;WINDOW=65536


def summary(samples,stages,setup):
    if (set(samples)!=set(MODES)or set(stages)!=set(MODES)or set(setup)!=set(MODES)
            or any(len(samples[m])!=ROUNDS or len(stages[m])!=ROUNDS for m in MODES)):
        raise ValueError('twenty-four complete geometry samples per mode required')
    if (any(type(v)not in(int,float)or not 0<v<float('inf')for values in samples.values()for v in values)
            or any(type(v)not in(int,float)or not 0<=v<float('inf')for v in setup.values())):
        raise ValueError('invalid geometry timing sample')
    medians={m:statistics.median(samples[m])for m in MODES}
    totals={m:sum(samples[m])+setup[m]for m in MODES}
    fastest=min(MODES,key=lambda m:totals[m])
    return dict(rounds=ROUNDS,tiles_per_nonce_per_mode=WINDOW,unique_timed_tiles_per_mode=ROUNDS*WINDOW,
        median_cycle_seconds=medians,initial_geometry_seconds=setup,total_seconds_including_geometry=totals,
        amortized_speedup_over_v062={m:totals[MODES[0]]/totals[m]for m in MODES},
        median_phase_seconds={m:{p:statistics.median(row[p]for row in stages[m])for p in('setup','search','close')}for m in MODES},
        preferred=fastest if totals[fastest]<.97*totals[MODES[0]]else MODES[0],
        scope=f'fresh nonce setup + {WINDOW} search tiles + cleanup; includes one geometry build per cached mode; not full-nonce or whole-miner speedup')


def run_window(search):
    for offset in range(0,WINDOW,4096):
        hit,cursor=search.advance(4096)
        if hit is not None or cursor.next_tile!=offset+4096:raise RuntimeError('geometry comparison candidate/cursor differs')
    return cursor.next_tile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--commitment-module',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,gpu_scanner='shared-B-v060',
        scope='nonce lifecycle and setup experiment; same contexts/ranges; not steady-state GPU or whole-miner speedup',
        common_preparation_excluded='B commitment, verified nonce frontier, one B-table build, per-round nonce context and CUDA start/JIT')
    session=device=b_owner=None;owners={};search=None
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
        b_owner=JobBTables(device,context,session.is_current)
        for mode,maps in zip(MODES[1:],(False,True)):owners[mode]=JobGeometry(device,job,session.is_current,maps=maps)
        setup={MODES[0]:0.,**{mode:owner.setup_seconds for mode,owner in owners.items()}}
        def factory(mode,context):
            if mode==MODES[0]:return new_job_b_search(context,device,session.is_current,b_owner)
            return new_geometry_search(context,device,session.is_current,b_owner,owners[mode])
        for mode in MODES:
            with factory(mode,context)as search:run_window(search)
            search=None
        samples={m:[]for m in MODES};stages={m:[]for m in MODES}
        for index in range(ROUNDS):
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            for mode in ORDERS[index%len(ORDERS)]:
                started=time.perf_counter();search=factory(mode,context);prepared=time.perf_counter()
                try:
                    if search.context is not context:raise RuntimeError('geometry nonce context changed')
                    run_window(search);scanned=time.perf_counter()
                finally:search.close();search=None
                closed=time.perf_counter();samples[mode].append(closed-started)
                stages[mode].append(dict(setup=prepared-started,search=scanned-prepared,close=closed-scanned))
            print('Geometry comparison round',str(index+1)+'/24 complete.',flush=True)
        counts={};setup_counts={}
        for mode in MODES:
            with DriverCounts(device)as counter:search=factory(mode,context)
            setup_counts[mode]=counter.report()
            try:
                with DriverCounts(device)as counter:run_window(search)
                counts[mode]=counter.report()
            finally:search.close();search=None
        for mode in MODES:
            calls=counts[mode]['calls'];copies=counts[mode]['copy_bytes']
            if (calls.get('cuMemcpyDtoH_v2',0)!=16 or copies.get('cuMemcpyDtoH_v2',0)!=8064
                    or calls.get('cuLaunchKernel',0)!=32 or calls.get('cuStreamSynchronize',0)!=16
                    or calls.get('cuMemcpyHtoD_v2',0)!=0 or calls.get('cuCtxSynchronize',0)!=0
                    or calls.get('cuMemsetD32Async',0)!=16):raise RuntimeError('geometry window protocol differs: '+mode)
        uploaded={m:setup_counts[m]['copy_bytes'].get('cuMemcpyHtoD_v2',0)for m in MODES}
        map_bytes=owners[MODES[2]].upload_bytes
        if uploaded[MODES[0]]!=uploaded[MODES[1]]or uploaded[MODES[0]]-uploaded[MODES[2]]!=2*map_bytes+64:
            raise RuntimeError('geometry setup did not remove exactly two map initializations and uploads')
        report['readback_contract_checked']=True;report['map_upload_savings_checked']=True
        report['contexts_and_ranges_identical']=True
        report['geometry_comparison']=summary(samples,stages,setup)
        report['cycle_samples_seconds']=samples;report['phase_samples_seconds']=stages
        report['driver_diagnostic']=dict(tiles_per_mode=WINDOW,separate_from_primary_timings=True,modes=counts)
        report['setup_driver_diagnostic']=dict(separate_from_primary_timings=True,modes=setup_counts,
            map_payload_bytes=map_bytes,saved_host_upload_bytes_per_reused_nonce=2*map_bytes+64)
        for owner in owners.values():owner.close()
        report['geometry_owners']={m:o.stats()for m,o in owners.items()}
        owners={};b_owner.close();b_owner=None
        if device.allocations:raise RuntimeError('geometry comparison leaked GPU allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        for resource in (search,*owners.values(),b_owner,device):
            if resource is not None:
                try:resource.close()
                except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('GEOMETRY COMPARISON:',json.dumps(report['geometry_comparison']),flush=True)
    print('DRIVER COUNTS:',json.dumps(report['driver_diagnostic']),flush=True)
    print('SETUP DRIVER COUNTS:',json.dumps(report['setup_driver_diagnostic']),flush=True)
    print('Offline comparison complete. GPU math unchanged; no pool connection or shares.',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
