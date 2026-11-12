#!/usr/bin/env python3
"""v078 independent equal-work speed comparison and separate sustained GPU-energy trials. ISC."""
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
from tools.compare_experiments import resources,run_window
from tools.throughput_scan import new_search,MODES,LIMITS,GROUPS
from tools.gpu_power import NvmlReader,PowerSampler,TelemetryError
WINDOW=1048576
ROUNDS=12
# Four balanced orders: each mode occupies every position and precedes every other mode.
ORDERS=tuple(tuple(MODES[i]for i in order)for order in ((0,1,3,2),(1,2,0,3),(2,3,1,0),(3,0,2,1)))
FULL_NONCE=8388608


def summary(samples,setup,tiles):
    if tuple(samples)!=MODES or len({len(v)for v in samples.values()})!=1:raise ValueError('invalid comparison modes or sample counts')
    if any(not values or any(type(v)not in(int,float)or not math.isfinite(v)or v<=0 for v in values)for values in samples.values()):raise ValueError('invalid timing')
    medians={m:statistics.median(samples[m])for m in MODES};speed={m:medians[MODES[0]]/medians[m]for m in MODES}
    preferred={}
    for group,modes in GROUPS.items():
        fastest=min(modes,key=lambda m:medians[m]);preferred[group]=fastest if speed[fastest]>1/.97 else MODES[0]
    return dict(rounds=len(samples[MODES[0]]),tiles_per_round_per_mode=tiles,unique_timed_tiles_per_mode=tiles*len(samples[MODES[0]]),
        median_seconds=medians,median_tiles_per_second={m:tiles/medians[m]for m in MODES},speedup_over_wide16k=speed,
        independent_preferred=preferred,setup_seconds=setup,wall_samples_seconds=samples)


def diagnostic(search):
    with DriverCounts(search.backend.dispatch.device)as counter:span=run_window(search,WINDOW)
    report=counter.report();calls=report['calls'];copied=report['copy_bytes'];expected=WINDOW//LIMITS[search.mode]
    if (span[0]%WINDOW or span[1]%WINDOW or calls.get('cuLaunchKernel',0)!=2*expected
            or calls.get('cuMemsetD32Async',0)!=expected or calls.get('cuStreamSynchronize',0)!=expected
            or calls.get('cuMemcpyDtoH_v2',0)!=expected or copied.get('cuMemcpyDtoH_v2',0)!=expected*504
            or calls.get('cuMemcpyHtoD_v2',0)or calls.get('cuCtxSynchronize',0)):
        raise RuntimeError('mode-specific driver contract differs: '+search.mode)
    report['range']=span;return report


def efficiency_summary(trials):
    result={}
    for mode in MODES:
        rows=[row['measurement']for row in trials if row['mode']==mode]
        if len(rows)!=2 or not all(row.get('available')is True for row in rows):
            result[mode]=dict(available=False);continue
        energy=sum(r['energy_joules']for r in rows);seconds=sum(r['seconds']for r in rows);tiles=sum(r['measured_tiles']for r in rows)
        out=dict(available=True,measured_tiles=tiles,seconds=seconds,energy_joules=energy,average_power_w=energy/seconds,
            tiles_per_joule=tiles/energy,tiles_per_second_including_nonce_setup=tiles/seconds,
            maximum_temperature_c=max(r['maximum_temperature_c']for r in rows)if all(r['maximum_temperature_c']is not None for r in rows)else None)
        for field in ('gpu_activity_pct','memory_activity_pct','sm_clock_mhz','memory_clock_mhz','temperature_c','power_limit_w'):
            key='average_'+field
            out[key]=sum(r[key]*r['seconds']for r in rows)/seconds if all(r[key]is not None for r in rows)else None
        out['clock_limit_time_fraction']={key:(sum(r['clock_limit_time_fraction'][key]*r['seconds']for r in rows)/seconds
            if all(r['clock_limit_time_fraction'][key]is not None for r in rows)else None)for key in rows[0]['clock_limit_time_fraction']}
        result[mode]=out
    if all(r['available']for r in result.values()):
        base=result[MODES[0]]['tiles_per_joule']
        for row in result.values():row['efficiency_over_wide16k']=row['tiles_per_joule']/base
    return result


def power_phase(device,job,base,frontier,session,owners):
    report=dict(attempted=True,available=False,error=None,trials=[],scope='GPU-board energy for fresh nonce preparation + A setup + full search + nonce cleanup; initial per-job context/base/B/geometry excluded',
        interval_seconds=.2,conditioning_nonces_per_trial=1,measured_nonces_per_trial=3,rounds=2,
        power_source='NVML board-power readings, trapezoidal integration; approximate sensor estimate, not wall-plug energy',
        utilization_meaning='kernel-active time and memory-active time; not achieved Tensor Core or memory bandwidth utilization')
    reader=None
    try:
        reader=NvmlReader(device);report['pci_bus_id']=reader.pci_bus_id;reader.read()
        def nonce_work(mode,nonces):
            geometry,b_owner=owners[mode]
            for nonce in nonces:
                context=prepare_cached_nonce(job,base,b'TESTWORK',nonce,session.is_current,frontier)
                with new_search(context,device,session.is_current,b_owner,geometry,mode=mode)as search:
                    if search.plan.count!=FULL_NONCE:raise RuntimeError('power comparison requires full production domain')
                    if run_window(search,FULL_NONCE)!=(0,FULL_NONCE):raise RuntimeError('power work set differs')
        for round_id,order in enumerate((MODES,tuple(reversed(MODES)))):
            nonces=tuple(secrets.token_bytes(8)for _ in range(3));conditioning=(secrets.token_bytes(8),)
            for mode in order:
                nonce_work(mode,conditioning)
                sampler=PowerSampler(reader)
                measurement=sampler.measure(lambda:nonce_work(mode,nonces),3*FULL_NONCE)
                report['trials'].append(dict(mode=mode,round=round_id+1,nonces_hex=[n.hex()for n in nonces],measurement=measurement))
                print('POWER',mode,'round',str(round_id+1)+'/2 complete.',flush=True)
        report['summary']=efficiency_summary(report['trials'])
        report['available']=all(r['available']for r in report['summary'].values())
        if not report['available']:report['error']='one or more energy windows lacked valid sample coverage; no efficiency winner selected'
    except TelemetryError as error:
        report['error']=str(error)
    finally:
        if reader is not None:reader.close()
    if report['available']:
        report['most_efficient']=max(MODES,key=lambda m:report['summary'][m]['tiles_per_joule'])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','report'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,experiment='throughput',
        power_monitoring_attempted=False,scope='balanced equal canonical work; actual v074 wide16k kernel and 16K host dispatch as control; speed timing excludes setup and telemetry')
    session=device=None;searches={};owners={};owned=[]
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        setup={mode:0. for mode in MODES};resource_report={};samples={mode:[]for mode in MODES};ranges=[];nonces=[]
        for epoch in range(2):
            nonce=secrets.token_bytes(8)
            while nonce.hex()in nonces:nonce=secrets.token_bytes(8)
            nonces.append(nonce.hex())
            context=prepare_cached_nonce(job,base,b'TESTWORK',nonce,session.is_current,frontier)
            for mode in MODES:
                if epoch==0:
                    geometry=JobGeometry(device,job,session.is_current,maps=True);owned.append(geometry)
                    b_owner=JobBTables(device,context,session.is_current);owned.append(b_owner);owners[mode]=(geometry,b_owner)
                else:geometry,b_owner=owners[mode]
                started=time.perf_counter();search=new_search(context,device,session.is_current,b_owner,geometry,mode=mode)
                searches[mode]=search;setup[mode]+=time.perf_counter()-started
                observed_resources=resources(search.backend.dispatch)
                if epoch==0:resource_report[mode]=observed_resources
                elif resource_report[mode]!=observed_resources:raise RuntimeError('kernel resources changed across nonces')
            for mode in MODES:run_window(searches[mode],WINDOW)
            for local in range(6):
                round_id=epoch*6+local;observed={}
                for mode in ORDERS[round_id%4]:
                    started=time.perf_counter();observed[mode]=run_window(searches[mode],WINDOW)
                    samples[mode].append(time.perf_counter()-started)
                    print('THROUGHPUT',mode,'round',str(round_id+1)+'/12 complete.',flush=True)
                if len(set(observed.values()))!=1:raise RuntimeError('comparison work sets differ')
                first,stop=observed[MODES[0]]
                if first%WINDOW or stop%WINDOW:raise RuntimeError('noncanonical work window')
                ranges.append(dict(nonce_hex=nonce.hex(),first=first,stop=stop))
            if epoch==1:counts={mode:diagnostic(searches[mode])for mode in MODES}
            for search in searches.values():search.close()
            searches={}
        report.update(comparison=summary(samples,setup,WINDOW),kernel_resources=resource_report,driver_diagnostic=counts,
            canonical_work_sets_checked=True,readback_contract_checked=True,timed_ranges=ranges,speed_nonce_hex=nonces,whole_64_row_groups_checked=True)
        for search in searches.values():search.close()
        searches={};report['power_monitoring_attempted']=True
        report['power']=power_phase(device,job,base,frontier,session,owners)
        for owner in owned:owner.close()
        owned=[];owners={}
        if device.allocations:raise RuntimeError('throughput comparison leaked allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        for obj in [*searches.values(),*owned,device]:
            if obj is not None:
                try:obj.close()
                except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('THROUGHPUT RESULT:',json.dumps({k:v for k,v in report['comparison'].items()if k!='wall_samples_seconds'}),flush=True)
    print('POWER RESULT:',json.dumps({k:v for k,v in report['power'].items()if k!='trials'}),flush=True)
    print('KERNEL RESOURCES:',json.dumps(report['kernel_resources']),flush=True)
    print('DRIVER COUNTS:',json.dumps(report['driver_diagnostic']),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
