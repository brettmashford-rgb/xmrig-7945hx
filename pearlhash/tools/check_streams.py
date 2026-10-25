#!/usr/bin/env python3
"""One versus two nonblocking streams, identical cached-A windows; offline. ISC."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.cached_a import CachedA,attach
from tools.stream_scan import StreamDispatch,execute_pair
from tools.prepared_dispatch import PreparedDispatch,KERNELS
from tools.production_scan import ProductionCandidateScanner
from tools.virtual_scan import VirtualTables,global_reference
from tools.check_production_gpu import cases
from tools.check_warp_gpu import expected_transcripts
from tools.check_tile_scan_gpu import MAX_BOUND
from tools.fast_plan import FastPlan
from pool.session import MiningProfile
from reference.patterns import PeriodicPattern


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report={'complete':False,'error':None,'pool_connection':False,'submitted_shares':0,'cases':[],
            'scope':'offline identical synthetic production windows; no bandwidth saturation or mining throughput claim'}
    device=tables=cache=baseline=None;lanes=[]
    def clear():
        nonlocal tables,cache,baseline,lanes
        # Drain every stream before shared A/noise data can be released.
        for lane in lanes:lane.wait()
        for resource in [*lanes,baseline,cache,tables]:
            if resource is not None:resource.close()
        lanes=[];tables=cache=baseline=None
    try:
        device=ProductionCandidateScanner();device.start(args.module)
        for name,profile,unique,count in cases():
            refs=dict(zip(unique,global_reference(profile,unique)))
            queries=tuple(unique[i%len(unique)]for i in range(67))
            tables=VirtualTables(device,profile);cache=CachedA(tables)
            for _ in range(2):
                lane=StreamDispatch(device,tables,KERNELS[0]);lanes.append(lane);attach(lane,cache)
            equal=[int.from_bytes(refs[q][1],'little')for q in queries]
            scenarios=(('hit',[MAX_BOUND]*67,67),('miss',[0]*67,0),('equality',equal,67),
                       ('zero-queue',[MAX_BOUND]*67,0),('overflow',equal,1))
            for label,bounds,capacity in scenarios:
                batches=tuple(lane.prepare(queries,bounds)for lane in lanes)
                results=execute_pair(lanes,batches,(1<<63)+41,True,capacity=capacity,audit=True)
                expected={i:refs[q][1]for i,q in enumerate(queries)if int.from_bytes(refs[q][1],'little')<=bounds[i]}
                for result,traces in results:
                    if (result.total!=len(expected)or result.overflow!=(len(expected)>capacity)
                            or traces!=expected_transcripts(refs,queries)):
                        raise RuntimeError('parallel CPU transcript/count/overflow mismatch')
                    if result.overflow:
                        if len(result.records)!=capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                            raise RuntimeError('parallel partial queue mismatch')
                    elif result.records!=expected:raise RuntimeError('parallel candidate set mismatch')
                report['cases'].append({'profile':name,'case':label,'passed':True})
            clear();print('PASS: two streams:',name,'CPU transcripts, targets, queues and guards.',flush=True)
        profile=list(cases())[1][1]
        job=SimpleNamespace(profile=MiningProfile(profile.m,profile.n,32768,128,
            PeriodicPattern(bytes.fromhex('000103040000')),PeriodicPattern(bytes.fromhex('000103010103'))))
        plan=FastPlan.from_job(job);tables=VirtualTables(device,profile);cache=CachedA(tables)
        baseline=PreparedDispatch(device,tables,KERNELS[0]);attach(baseline,cache)
        for _ in range(2):
            lane=StreamDispatch(device,tables,KERNELS[0]);lanes.append(lane);attach(lane,cache)
        for first in (0,plan.count//2,plan.count-8192):
            windows=tuple(next(plan.batches(first+i*4096,first+(i+1)*4096))for i in range(2))
            expected=[]
            for batch in windows:
                result=baseline.run(plan.prepare(baseline.token,batch,0,4096),41,capacity=0,audit=True)
                if result.total:raise RuntimeError('unexpected zero-bound hit')
                expected.append(device.last_transcripts)
            batches=tuple(plan.prepare(lane.token,batch,0,4096)for lane,batch in zip(lanes,windows))
            results=execute_pair(lanes,batches,41,True,audit=True)
            if any(result.total or traces!=words for (result,traces),words in zip(results,expected)):
                raise RuntimeError('parallel full production transcript mismatch')
        print('PASS: both full windows match v040 at first/middle/end.',flush=True)
        samples={'one_stream':[],'two_streams':[]};launch_samples={'one_stream':[],'two_streams':[]}
        # Untimed warmup of each scheduling mode, then alternating-order trials.
        for round_id in range(-2,20):
            first=((max(0,round_id)*8192)%(plan.count-8192))
            windows=tuple(next(plan.batches(first+i*4096,first+(i+1)*4096))for i in range(2))
            batches=tuple(plan.prepare(lane.token,batch,0,4096)for lane,batch in zip(lanes,windows))
            modes=('one_stream','two_streams')if round_id%2==0 else('two_streams','one_stream')
            for mode in modes:
                started=time.perf_counter()
                for lane,batch in zip(lanes,batches):lane.stage(batch,41,capacity=0)
                device.api('cuCtxSynchronize',[])
                launch_start=time.perf_counter()
                if mode=='two_streams':
                    for lane in lanes:lane.enqueue()
                    for lane in lanes:lane.wait()
                else:
                    # Same private buffers/work, but both kernels actually use
                    # lane zero's CUDA stream in the serial control.
                    for lane in lanes:
                        saved=lane.stream;lane.stream=lanes[0].stream
                        try:lane.enqueue();lane.wait()
                        finally:lane.stream=saved
                launch_time=time.perf_counter()-launch_start
                results=tuple(lane.finish()for lane in lanes)
                elapsed=time.perf_counter()-started
                if any(result.total or result.overflow for result,_ in results):raise RuntimeError('unexpected benchmark hit')
                if round_id>=0:samples[mode].append(elapsed);launch_samples[mode].append(launch_time)
            if round_id>=0:print('Stream comparison round',str(round_id+1)+'/20 complete.',flush=True)
        a=statistics.median(samples['one_stream']);b=statistics.median(samples['two_streams'])
        report['stream_comparison']={'rounds':20,'tiles_per_round_per_mode':8192,'unique_tiles_per_mode':20*8192,
            'one_stream_median_seconds':a,'two_streams_median_seconds':b,'speedup':a/b,
            'preferred':'two-streams'if b<a*.97 else'one-stream',
            'one_stream_tiles_per_second':8192/a,'two_streams_tiles_per_second':8192/b,
            'launch_and_wait_median_seconds':{k:statistics.median(v)for k,v in launch_samples.items()},
            'wall_samples_seconds':samples,'launch_and_wait_samples_seconds':launch_samples,
            'includes':'descriptor/target upload, reset, launch, wait, readback and guards; excludes shared nonce/cache setup and common descriptor planning',
            'a_cache_bytes':cache.bytes,'dispatch_buffer_sets':2,'bandwidth_saturation_measured':False}
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        try:clear()
        except Exception as exc:report['error']=report['error']or('cleanup: '+str(exc))
        if device is not None:
            try:device.close()
            except Exception as exc:report['error']=report['error']or('context cleanup: '+str(exc))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('STREAM COMPARISON:',json.dumps(report['stream_comparison']),flush=True)
    print('Offline comparison complete. No pool connection or shares sent.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
