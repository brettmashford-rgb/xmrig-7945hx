#!/usr/bin/env python3
"""V85 unchanged pair-direct baseline timing and isolated hardware-counter target. ISC."""
import argparse
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import time
BASE=Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path: sys.path.insert(0,str(BASE))
from tools.compare_cta_b import production_session
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.production_scan import ProductionCandidateScanner
from tools.job_geometry import JobGeometry
from tools.job_b_tables import JobBTables
from tools.pair_depth_scan import new_search
from tools.compare_experiments import resources,run_window
from tools.dispatch_profile import profile_control
from tools.gpu_power import NvmlReader,PowerSampler,TelemetryError
FULL=8388608


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','report'): parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--counter-target',action='store_true')
    args=parser.parse_args()
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,
        kernel='a_pair_direct_scan',counter_target=args.counter_target)
    session=device=None;owned=[];search=None
    try:
        session,job=production_session()
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
        geometry=JobGeometry(device,job,session.is_current,maps=True);owned.append(geometry)
        b=JobBTables(device,context,session.is_current);owned.append(b)
        search=new_search(context,device,session.is_current,b,geometry,start=FULL//2 if args.counter_target else 0)
        report['resources']=resources(search.backend.dispatch)
        if args.counter_target:
            # ncu filters this exact scanner, skips eight warm-up launches, profiles three.
            # All three are complete 16K windows near the middle of the production domain.
            report['range']=run_window(search,11*16384)
            report['warmup_windows']=8;report['profiled_windows']=3
            report['timing_is_profiler_perturbed']=True
        else:
            run_window(search,524288)
            samples=[]
            for i in range(8):
                before=time.perf_counter();run_window(search,524288)
                samples.append(time.perf_counter()-before)
                print('BASELINE timing',str(i+1)+'/8 complete.',flush=True)
            report['baseline']=dict(tiles_per_round=524288,rounds=8,
                median_tiles_s=524288/statistics.median(samples),samples_s=samples)
            report['host_gpu_profile']=profile_control(search)
            search.close();search=None
            def full_nonce():
                fresh=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
                with new_search(fresh,device,session.is_current,b,geometry) as whole:
                    if whole.plan.count!=FULL or run_window(whole,FULL)!=(0,FULL):
                        raise RuntimeError('full nonce work differs')
            full_nonce() # separate thermal conditioning nonce
            reader=None
            try:
                reader=NvmlReader(device);reader.read()
                report['board_energy']=PowerSampler(reader).measure(lambda:[full_nonce() for _ in range(3)],3*FULL)
                report['board_energy']['scope']='three full nonces including fresh nonce and A preparation; per-job B/geometry excluded; NVML sensor estimate'
            except TelemetryError as error: report['board_energy']=dict(available=False,error=str(error))
            finally:
                if reader is not None: reader.close()
        if search is not None:search.close();search=None
        for owner in reversed(owned):owner.close()
        owned=[]
        if device.allocations:raise RuntimeError('profile leaked device allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError) as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        for obj in [search,*reversed(owned),device,session]:
            if obj is not None:
                try:obj.close()
                except Exception as error:report['error']=report['error'] or ('cleanup: '+str(error))
        report['complete']=report['complete'] and report['error'] is None
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('COUNTER TARGET complete.' if args.counter_target else 'Unprofiled baseline and separate host/event diagnostic complete.',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
