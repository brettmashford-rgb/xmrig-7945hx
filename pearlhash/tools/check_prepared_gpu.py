#!/usr/bin/env python3
"""Offline reusable-dispatch correctness and changing-window comparison. ISC."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.profile_dispatch import ProfileScanner
from tools.prepared_dispatch import PreparedDispatch,KERNELS
from tools.cooperative_scan import CooperativeCache,cooperative_queries
from tools.virtual_scan import VirtualTables,global_reference
from tools.check_production_gpu import cases
from tools.check_warp_gpu import expected_transcripts
from tools.check_tile_scan_gpu import MAX_BOUND
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain

LABELS=('virtual','fragment','cooperative')


def grid(profile):
    ad=PatternDomain(profile.m,PeriodicPattern(bytes.fromhex('000103040000')))
    bd=PatternDomain(profile.n,PeriodicPattern(bytes.fromhex('000103010103')))
    rows=tuple(ad.indices(i*(ad.count-1)//63)for i in range(64))
    cols=tuple(bd.indices(i*(bd.count-1)//127)for i in range(128))
    queries=cooperative_queries(rows,cols)
    if len(queries)!=8192 or len(set(queries))!=8192:
        raise RuntimeError('expected 8192 distinct changing-window queries')
    # Cover all cached rows with <=4096 representative queries.
    cover=cooperative_queries(rows,cols[:8])+cooperative_queries(rows[:2],cols)
    return rows,cols,queries,cover


def totals(records):
    return {'wall_seconds':sum(r['wall_seconds']for r in records),
            'gpu_event_seconds':sum(r['gpu_event_seconds']for r in records),
            'preparation_seconds':sum(r.get('preparation_seconds',0.)for r in records),
            'allocation_calls':sum(r['api_counts'].get('cuMemAlloc_v2',0)for r in records),
            'python_seconds':sum(r['host_seconds']['python_and_bookkeeping']for r in records)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    device=tables=cache=None;dispatches={};error=None
    report={'complete':False,'submitted_shares':0,'correctness':[], 'repeated':{},'changing':{},
            'scope':'offline synthetic dispatch components, no live mining integration or pool verdict',
            'changing_unique_queries':8192,'changing_queries_per_window':1024,'repeated_queries_per_round':4096}
    try:
        device=ProfileScanner();device.start(args.module);device.create_events()
        profile=list(cases())[1][1];rows,cols,all_queries,cover=grid(profile)
        setup=time.perf_counter();tables=VirtualTables(device,profile)
        report['noise_setup_seconds']=time.perf_counter()-setup
        setup=time.perf_counter();cache=CooperativeCache(tables,cover)
        report['materialization_seconds']=time.perf_counter()-setup;report['cache_bytes']=cache.bytes
        for label,kernel in zip(LABELS,KERNELS):
            setup=time.perf_counter()
            dispatches[label]=PreparedDispatch(device,tables,kernel,cache=None if label=='virtual'else cache)
            report.setdefault('dispatch_setup_seconds',{})[label]=time.perf_counter()-setup
        def original(label,queries,bounds,capacity,generation,audit=False):
            if label=='virtual':return device.scan_wide(tables,queries,bounds,capacity,generation,audit=audit)
            cache.selected_scan_kernel=KERNELS[LABELS.index(label)]
            return device.scan_cached(cache,queries,bounds,capacity,generation,audit=audit)
        # The same production profile with first/last domain indices. Four
        # distinct global tiles, repeated within one collective-shaped block.
        small=cooperative_queries((rows[0],rows[-1]),tuple(cols[0]if i%2==0 else cols[-1]for i in range(8)))
        unique=tuple(dict.fromkeys(small));refs=dict(zip(unique,global_reference(profile,unique)))
        equal=tuple(int.from_bytes(refs[q][1],'little')for q in small)
        mixed=tuple(v if i%2==0 else max(0,v-1)for i,v in enumerate(equal))
        scenarios=(('all-hit',[MAX_BOUND]*16,16),('miss',[0]*16,0),('equality',equal,16),
                   ('zero-queue',[MAX_BOUND]*16,0),('overflow',mixed,1),('mixed-complete',mixed,16))
        for label,dispatch in dispatches.items():
            for name,bounds,capacity in scenarios:
                batch=dispatch.prepare(small,bounds)
                result=dispatch.run(batch,(1<<63)+35,capacity=capacity,audit=True)
                expected={i:refs[q][1]for i,q in enumerate(small)if int.from_bytes(refs[q][1],'little')<=bounds[i]}
                if (result.total!=len(expected)or result.overflow!=(len(expected)>capacity)
                        or device.last_transcripts!=expected_transcripts(refs,small)):
                    raise RuntimeError('prepared correctness count/transcript differs')
                if result.overflow:
                    if len(result.records)!=capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                        raise RuntimeError('partial candidate queue differs')
                elif result.records!=expected:raise RuntimeError('complete candidate queue differs')
                report['correctness'].append({'path':label,'case':name,'passed':True})
            print('PASS: prepared '+label+'; six CPU transcript/target/queue cases.',flush=True)
        queries=all_queries[:4096];bounds=[0]*4096;prepared={}
        reference=None
        for label,dispatch in dispatches.items():
            setup=time.perf_counter();prepared[label]=dispatch.prepare(queries,bounds)
            report.setdefault('initial_batch_prepare_seconds',{})[label]=time.perf_counter()-setup
            result=original(label,queries,bounds,0,35,audit=True)
            if result.total:raise RuntimeError('unexpected original grid candidate')
            if reference is None:reference=device.last_transcripts
            elif device.last_transcripts!=reference:raise RuntimeError('original grid transcripts differ')
            result=dispatch.run(prepared[label],35,capacity=0,audit=True)
            if result.total or device.last_transcripts!=reference:raise RuntimeError('prepared grid transcripts differ')
        print('PASS: full 4096-query transcripts match for original and prepared paths.',flush=True)
        # All six paths use the same query order, target, immutable noise/cache.
        labels=tuple((label,mode)for label in LABELS for mode in ('original','prepared'))
        for repeat in range(8):
            order=labels[repeat%6:]+labels[:repeat%6]
            for label,mode in order:
                operation=(lambda label=label:original(label,queries,bounds,0,repeat))if mode=='original'else(
                    lambda label=label:dispatches[label].run(prepared[label],repeat,capacity=0))
                result,measured=device.measure(operation)
                if result.total or result.overflow:raise RuntimeError('unexpected repeated timing candidate')
                report['repeated'].setdefault(label+'_'+mode,[]).append(measured)
        # Eight disjoint windows: every global tile here is searched once per
        # path, and each new batch is packed/uploaded inside its measured time.
        # Windows are intentionally 1024 queries, different from repeated case.
        for window in range(8):
            current=all_queries[window*1024:(window+1)*1024];targets=[0]*1024
            order=labels[window%6:]+labels[:window%6]
            for label,mode in order:
                started=time.perf_counter();prepare_time=0.
                if mode=='prepared':
                    batch=dispatches[label].prepare(current,targets)
                    prepare_time=time.perf_counter()-started
                    operation=lambda label=label,batch=batch:dispatches[label].run(batch,window+100,capacity=0)
                else:
                    operation=lambda label=label:original(label,current,targets,0,window+100)
                result,measured=device.measure(operation)
                measured['preparation_seconds']=prepare_time
                measured['wall_seconds']+=prepare_time
                # Preparation is outside the measured dispatch but included in
                # the host residual so host categories still sum to wall time.
                measured['host_seconds']['python_and_bookkeeping']+=prepare_time
                if result.total or result.overflow:raise RuntimeError('unexpected changing-window candidate')
                report['changing'].setdefault(label+'_'+mode,[]).append(measured)
            print('Changing-window comparison '+str(window+1)+'/8 complete.',flush=True)
        for kind in ('repeated','changing'):
            report[kind+'_totals']={key:totals(records)for key,records in report[kind].items()}
            for label in LABELS:
                before=report[kind+'_totals'][label+'_original'];after=report[kind+'_totals'][label+'_prepared']
                after['with_dispatch_and_cache_setup_seconds']=(after['wall_seconds']+
                    report['dispatch_setup_seconds'][label]+
                    (report['materialization_seconds']if label!='virtual'else 0.)+
                    (report['initial_batch_prepare_seconds'][label]if kind=='repeated'else 0.))
                if after['allocation_calls']!=0:raise RuntimeError('prepared timing allocated device memory')
                print(kind.upper()+' '+label+': original='+format(before['wall_seconds'],'.6f')+
                      's prepared='+format(after['wall_seconds'],'.6f')+
                      's GPU='+format(after['gpu_event_seconds'],'.6f')+
                      's prepare='+format(after['preparation_seconds'],'.6f')+'s with_setup='+format(after['with_dispatch_and_cache_setup_seconds'],'.6f')+'s allocations=0',flush=True)
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        for resource in (*dispatches.values(),cache,tables,device):
            if resource is not None:
                try:resource.close()
                except Exception as exc:error=error or('cleanup: '+str(exc))
        report['error']=error;report['complete']=report['complete']and error is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if error:print('STOP:',error,flush=True);return 1
    print('Reusable dispatch checks complete. Offline only; no shares sent.',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
