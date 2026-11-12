#!/usr/bin/env python3
"""v082 equal unique work over two real nonces; isolated reuse control and board energy. ISC."""
import argparse,ctypes as C,json,math,os,secrets,statistics,sys,time
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_cta_b import production_session,DriverCounts
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache
from tools.production_scan import ProductionCandidateScanner
from tools.compare_experiments import resources
from tools.gpu_power import NvmlReader,PowerSampler,TelemetryError
from tools.check_twin_b import contexts_for
from tools.twin_b_scan import Twin,JobInputs,MODES,LIMIT
WINDOW=524288
FULL_NONCE=8388608


def summary(samples,setup):
    if tuple(samples)!=MODES or any(len(v)!=12 for v in samples.values()):raise ValueError('twelve rounds per mode required')
    if any(type(v)not in(int,float)or not math.isfinite(v)or v<=0 for values in samples.values()for v in values):raise ValueError('invalid timings')
    medians={m:statistics.median(samples[m])for m in MODES};speed={m:medians[MODES[0]]/medians[m]for m in MODES}
    preferred='twin-shared-b'if speed['twin-shared-b']>1/.97 else 'pair-direct'
    return dict(rounds=12,nonces_per_trial=2,tiles_per_round_per_nonce=WINDOW,unique_tiles_per_round=2*WINDOW,
        unique_timed_tiles_per_mode=24*WINDOW,median_seconds=medians,median_unique_tiles_per_second={m:2*WINDOW/medians[m]for m in MODES},
        speedup_over_pair_direct=speed,reuse_speedup_over_matched_private=medians['twin-private-b']/medians['twin-shared-b'],
        preferred=preferred,matched_private_is_diagnostic_only=True,setup_seconds=setup,wall_samples_seconds=samples)


def diagnostic(twin,mode):
    with DriverCounts(twin.device)as counter:twin.run(mode,14*WINDOW,15*WINDOW)
    report=counter.report();calls=report['calls'];copies=report['copy_bytes'];windows=WINDOW//LIMIT
    if (calls.get('cuLaunchKernel',0)!=(4 if mode=='pair-direct'else 3)*windows
            or calls.get('cuMemsetD32Async',0)!=2*windows
            or calls.get('cuStreamSynchronize',0)!=(2 if mode=='pair-direct'else 1)*windows
            or calls.get('cuMemcpyDtoH_v2',0)!=2*windows or copies.get('cuMemcpyDtoH_v2',0)!=1008*windows
            or calls.get('cuMemcpyHtoD_v2',0)or calls.get('cuCtxSynchronize',0)):
        raise RuntimeError('two-nonce driver/guard readback contract differs: '+mode)
    return report


def efficiency_summary(trials):
    result={}
    for mode in MODES:
        rows=[t['measurement']for t in trials if t['mode']==mode]
        if len(rows)!=2 or not all(r.get('available')is True for r in rows):result[mode]=dict(available=False);continue
        energy=sum(r['energy_joules']for r in rows);seconds=sum(r['seconds']for r in rows);tiles=sum(r['measured_tiles']for r in rows)
        if tiles!=12*FULL_NONCE:raise RuntimeError('full-nonce energy work differs')
        out=dict(available=True,measured_tiles=tiles,seconds=seconds,energy_joules=energy,
            average_power_w=energy/seconds,tiles_per_joule=tiles/energy,unique_tiles_s_including_pair_setup=tiles/seconds)
        for field in('gpu_activity_pct','memory_activity_pct','sm_clock_mhz','memory_clock_mhz','temperature_c','power_limit_w'):
            key='average_'+field
            out[key]=sum(r[key]*r['seconds']for r in rows)/seconds if all(r[key]is not None for r in rows)else None
        out['maximum_temperature_c']=max(r['maximum_temperature_c']for r in rows)if all(r['maximum_temperature_c']is not None for r in rows)else None
        out['clock_limit_time_fraction']={key:sum(r['clock_limit_time_fraction'][key]*r['seconds']for r in rows)/seconds
            if all(r['clock_limit_time_fraction'][key]is not None for r in rows)else None for key in rows[0]['clock_limit_time_fraction']}
        result[mode]=out
    if all(v['available']for v in result.values()):
        for row in result.values():row['efficiency_over_pair_direct']=row['tiles_per_joule']/result['pair-direct']['tiles_per_joule']
    return result


def power_phase(device,job,base,front,session,inputs):
    report=dict(attempted=True,available=False,error=None,trials=[],interval_seconds=.2,rounds=2,
        conditioning_pairs_per_trial=1,measured_pairs_per_trial=3,distinct_nonces_per_pair=2,
        scope='fresh pair commitment/A setup + both full nonce scans + cleanup; initial per-job base/B/maps excluded',
        power_source='NVML board-power samples, approximate energy; not wall-plug power',
        utilization_meaning='kernel/memory activity; does not measure Tensor Core saturation')
    reader=None
    try:
        reader=NvmlReader(device);report['pci_bus_id']=reader.pci_bus_id;reader.read()
        def work(mode,pairs):
            for miners in pairs:
                from tools.nonce_cache import prepare_cached_nonce
                contexts=tuple(prepare_cached_nonce(job,base,b'TESTWORK',miner,session.is_current,front)for miner in miners)
                with Twin(contexts,device,session.is_current,inputs)as twin:
                    if twin.plan.count!=FULL_NONCE:raise RuntimeError('full nonce domain differs')
                    twin.run(mode,0,FULL_NONCE)
                    if twin.completed_unique_tiles!=2*FULL_NONCE:raise RuntimeError('incomplete pair energy work')
        for round_id,order in enumerate((MODES,tuple(reversed(MODES)))):
            pairs=tuple(tuple(secrets.token_bytes(8)for _ in range(2))for _ in range(3))
            conditioning=(tuple(secrets.token_bytes(8)for _ in range(2)),)
            for mode in order:
                work(mode,conditioning)
                measurement=PowerSampler(reader).measure(lambda:work(mode,pairs),6*FULL_NONCE)
                report['trials'].append(dict(mode=mode,round=round_id+1,measurement=measurement))
                print('POWER',mode,'round',str(round_id+1)+'/2 complete.',flush=True)
        report['summary']=efficiency_summary(report['trials']);report['available']=all(r['available']for r in report['summary'].values())
        if report['available']:report['most_efficient']=max(MODES,key=lambda m:report['summary'][m]['tiles_per_joule'])
        else:report['error']='energy sample coverage unavailable; no efficiency conclusion'
    except TelemetryError as error:report['error']=str(error)
    finally:
        if reader is not None:reader.close()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in('module','commitment-module','report'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,experiment='twin-b',power_monitoring_attempted=False,
        scope='two independent nonce domains with exact pair-direct traversal; setup excluded from speed, included in power')
    session=device=inputs=twin=None
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        front=NonceCommitmentCache.build(job,session.is_current);contexts=contexts_for(job,base,front,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module);inputs=JobInputs(device,contexts[0],session.is_current)
        start=time.perf_counter();twin=Twin(contexts,device,session.is_current,inputs);setup=time.perf_counter()-start
        resource={}
        for mode in MODES:
            d=twin.dispatches[0]
            target=d if mode=='pair-direct'else SimpleNamespace(device=device,function=twin.functions[mode],block_threads=512,mode=mode,guard_count=56,limit=2*LIMIT)
            resource[mode]=resources(target);twin.run(mode,0,WINDOW)
        samples={m:[]for m in MODES};orders=tuple(permutations(MODES));ranges=[]
        for round_id in range(12):
            first=(round_id+1)*WINDOW;stop=first+WINDOW
            for mode in orders[round_id%6]:
                start=time.perf_counter();observed=twin.run(mode,first,stop);samples[mode].append(time.perf_counter()-start)
                if observed!=(first,stop):raise RuntimeError('nonce pair work intervals differ')
                print('TWIN B',mode,'round',str(round_id+1)+'/12 complete.',flush=True)
            ranges.append((first,stop))
        counts={m:diagnostic(twin,m)for m in MODES}
        report.update(comparison=summary(samples,setup),kernel_resources=resource,driver_diagnostic=counts,timed_nonce_intervals=ranges,
            canonical_work_sets_checked=True,independent_nonce_bindings_checked=True,readback_contract_checked=True)
        twin.close();twin=None;report['power_monitoring_attempted']=True
        report['power']=power_phase(device,job,base,front,session,inputs)
        inputs.close();inputs=None
        if device.allocations:raise RuntimeError('two-nonce comparison leaked allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        for obj in(twin,inputs,device,session):
            if obj is not None:
                try:obj.close()
                except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as f:json.dump(report,f,indent=2);f.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('TWIN B RESULT:',json.dumps({k:v for k,v in report['comparison'].items()if k!='wall_samples_seconds'}),flush=True)
    print('POWER RESULT:',json.dumps({k:v for k,v in report['power'].items()if k!='trials'}),flush=True)
    print('KERNEL RESOURCES:',json.dumps(report['kernel_resources']),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
