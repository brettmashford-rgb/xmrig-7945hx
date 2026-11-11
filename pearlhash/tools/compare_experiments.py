#!/usr/bin/env python3
"""Pair/triple comparisons with measured occupancy; panel preparation included. ISC."""
import argparse
import ctypes as C
from itertools import permutations
import json
import math
import os
from pathlib import Path
import secrets
import statistics
import sys
import time
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_cta_b import production_session,DriverCounts
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.production_scan import ProductionCandidateScanner
from tools.job_geometry import JobGeometry
from tools.job_b_tables import JobBTables
from tools.b_quad_scan import kernel_resources
from tools.experiments_scan import new_search

GROUPS={'blocks':('control','small4','small8'),'pipeline':('control','pipeline'),
        'batching':('control','wide16k'),'panel':('control','panel-control','panel')}
WINDOW=524288


def resources(dispatch):
    result=kernel_resources(dispatch);blocks=C.c_int()
    dispatch.device.api('cuOccupancyMaxActiveBlocksPerMultiprocessor',[C.POINTER(C.c_int),C.c_void_p,C.c_int,C.c_size_t],
        C.byref(blocks),dispatch.function,dispatch.block_threads,0)
    if blocks.value<1:raise RuntimeError('kernel has no resident blocks')
    result.update(threads_per_block=dispatch.block_threads,max_active_blocks_per_sm=blocks.value,
        max_resident_warps_per_sm=blocks.value*(dispatch.block_threads//32),
        max_consumer_warps_per_sm=blocks.value*(8 if dispatch.mode=='pipeline'else dispatch.block_threads//32),
        guard_count=dispatch.guard_count,dispatch_limit=dispatch.limit)
    return result


def run_window(search,tiles):
    first=search.cursor.next_tile
    hit,cursor=search.advance(tiles)
    if hit is not None or cursor.next_tile!=first+tiles:raise RuntimeError('unexpected candidate or incomplete comparison range')
    return first,cursor.next_tile


def summary(samples,setup,tiles):
    modes=tuple(samples)
    if not modes or modes[0]!='control' or len({len(v)for v in samples.values()})!=1:raise ValueError('invalid samples')
    if any(not values or any(type(v)not in(int,float)or not math.isfinite(v)or v<=0 for v in values)for values in samples.values()):raise ValueError('invalid timing')
    medians={m:statistics.median(samples[m])for m in modes};speed={m:medians['control']/medians[m]for m in modes}
    fastest=min(modes,key=lambda m:medians[m]);preferred=fastest if speed[fastest]>1/.97 else 'control'
    result=dict(rounds=len(samples['control']),tiles_per_round_per_mode=tiles,
        unique_timed_tiles_per_mode=tiles*len(samples['control']),median_seconds=medians,
        median_tiles_per_second={m:tiles/medians[m]for m in modes},speedup_over_control=speed,preferred=preferred,
        setup_seconds=setup,wall_samples_seconds=samples)
    if 'panel'in modes:result['panel_speedup_over_same_traversal_control']=medians['panel-control']/medians['panel']
    return result


def diagnostic(search,tiles):
    d=search.backend.dispatch;before=d.panel_builds
    with DriverCounts(d.device)as counter:span=run_window(search,tiles)
    report=counter.report();calls=report['calls'];copied=report['copy_bytes'];built=d.panel_builds-before
    expected=(tiles+16383)//16384 if search.mode=='wide16k'else (tiles+4095)//4096
    read_size=d.snapshot[2]+32
    if (calls.get('cuLaunchKernel',0)!=2*expected+built or calls.get('cuMemsetD32Async',0)!=expected
            or calls.get('cuStreamSynchronize',0)!=expected+built
            or calls.get('cuMemcpyDtoH_v2',0)!=expected+built
            or copied.get('cuMemcpyDtoH_v2',0)!=expected*read_size+built*min(16,len(search.plan.cols))*4
            or calls.get('cuMemcpyHtoD_v2',0)or calls.get('cuCtxSynchronize',0)):
        raise RuntimeError('experimental driver contract differs: '+search.mode)
    report.update(panel_builds=built,range=span,snapshot_bytes=read_size)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','report'):parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--experiment',choices=GROUPS,required=True);args=parser.parse_args()
    fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    modes=GROUPS[args.experiment];report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,
        experiment=args.experiment,scope='same job, fresh nonce per panel round, exact canonical work; common experimental host driver with actual v070 kernel control',
        includes='search, checks, waits and readbacks; panel build kernels, flags and all panel switches included',
        excludes='initial context/JIT and nonce/A preparation; setup reported separately',cold_panel_builds_included=True)
    session=device=None;owners={};searches={};owned_objects=[]
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
        for mode in modes:
            geometry=JobGeometry(device,job,session.is_current,maps=True);owned_objects.append(geometry)
            b_owner=JobBTables(device,context,session.is_current);owned_objects.append(b_owner)
            owners[mode]=(geometry,b_owner)
        panel=args.experiment=='panel';rounds=6 if panel else 12;tiles=8388608 if panel else WINDOW
        samples={m:[]for m in modes};setup={m:[]for m in modes};stage={m:[]for m in modes};orders=tuple(permutations(modes))
        resource_report={};counts={};ranges=[]
        def create(mode,context):
            started=time.perf_counter();geometry,b_owner=owners[mode]
            search=new_search(context,device,session.is_current,b_owner,geometry,mode=mode)
            setup[mode].append(time.perf_counter()-started)
            try:
                if mode not in resource_report:resource_report[mode]=resources(search.backend.dispatch)
                return search
            except BaseException:search.close();raise
        if not panel:
            
            for mode in modes:searches[mode]=create(mode,context)
            for mode in modes:run_window(searches[mode],WINDOW)
        for round_id in range(rounds):
            if panel:
                context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
                for mode in modes:searches[mode]=create(mode,context)
            observed={}
            for mode in orders[round_id%len(orders)]:
                search=searches[mode];before=search.backend.stats();d=search.backend.dispatch;builds=d.panel_builds;panel_seconds=d.panel_seconds
                started=time.perf_counter();observed[mode]=run_window(search,tiles);elapsed=time.perf_counter()-started
                samples[mode].append(elapsed);after=search.backend.stats()
                stage[mode].append(dict(dispatches=after['dispatches']-before['dispatches'],panel_builds=d.panel_builds-builds,
                    panel_seconds=d.panel_seconds-panel_seconds))
                if panel and mode=='panel'and d.panel_builds-builds!=1024:raise RuntimeError('full nonce did not build exactly 1024 B panels')
                print(args.experiment,mode,'round',str(round_id+1)+'/'+str(rounds),'complete.',flush=True)
            if len(set(observed.values()))!=1:raise RuntimeError('comparison ranges differ')
            first,stop=observed[modes[0]]
            if panel:
                if (first,stop)!=(0,8388608):raise RuntimeError('panel comparison omitted canonical domain')
            elif first%(32*16384)or stop%(32*16384):raise RuntimeError('noncanonical timed row group')
            ranges.append((first,stop))
            if panel:
                for search in searches.values():search.close()
                searches={}
        if panel:
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            for mode in modes:searches[mode]=create(mode,context)
            # A cold, whole-domain diagnostic includes every panel build and flag read.
            for mode in modes:counts[mode]=diagnostic(searches[mode],tiles)
        else:
            for mode in modes:counts[mode]=diagnostic(searches[mode],WINDOW)
        report.update(kernel_resources=resource_report,driver_diagnostic=counts,canonical_work_sets_checked=True,
            readback_contract_checked=True,comparison=summary(samples,setup,tiles),stage_samples=stage,timed_ranges=ranges)
        for search in searches.values():search.close()
        searches={}
        for pair in owners.values():
            for owner in pair:owner.close()
        owners={};owned_objects=[]
        if device.allocations:raise RuntimeError('experimental comparison leaked allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        for obj in [*searches.values(),*owned_objects,device]:
            if obj is not None:
                try:obj.close()
                except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    compact={k:v for k,v in report['comparison'].items()if k!='wall_samples_seconds'}
    print(args.experiment.upper()+' COMPARISON:',json.dumps(compact),flush=True)
    print('KERNEL RESOURCES:',json.dumps(report['kernel_resources']),flush=True)
    print('DRIVER COUNTS:',json.dumps(report['driver_diagnostic']),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
