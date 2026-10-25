#!/usr/bin/env python3
"""New cached-input kernel correctness and same-input component comparison. ISC.

Offline synthetic seeds only. No pool connection, proof rebuild or shares.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.cached_scan import CachedCandidateScanner,RowCache
from tools.virtual_scan import VirtualTables,global_reference
from tools.check_production_gpu import cases
from tools.check_warp_gpu import expected_transcripts
from tools.check_tile_scan_gpu import MAX_BOUND,TileQuery
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    device=None;tables=None;cache=None;error=None;results=[];timing=None
    try:
        device=CachedCandidateScanner();device.start(args.module)
        for name,profile,unique,count in cases():
            print('Checking NEW materialized-input kernel: '+name,flush=True)
            refs=dict(zip(unique,global_reference(profile,unique)))
            queries=tuple(unique[i%len(unique)]for i in range(count))
            tables=VirtualTables(device,profile);cache=RowCache(tables,queries)
            equal=[int.from_bytes(refs[q][1],'little')for q in queries]
            mixed=[v if i%2==0 else max(0,v-1)for i,v in enumerate(equal)]
            scenarios=[('all-hit',[MAX_BOUND]*count,count),('all-miss',[0]*count,0),
                ('equality',equal,count),('zero-queue',[MAX_BOUND]*count,0),
                ('mixed-overflow',mixed,1),('mixed-complete',mixed,count)]
            for label,bounds,capacity in scenarios:
                expected={i:refs[q][1]for i,q in enumerate(queries)if int.from_bytes(refs[q][1],'little')<=bounds[i]}
                before=device.verified_tiles
                result=device.scan_cached(cache,queries,bounds,capacity,(1<<63)+31,audit=True)
                if result.total!=len(expected)or result.overflow!=(len(expected)>capacity):
                    raise RuntimeError('cached candidate count or overflow differs from CPU')
                if device.last_transcripts!=expected_transcripts(refs,queries):
                    raise RuntimeError('cached prefix transcript differs from independent CPU')
                if result.overflow:
                    if len(result.records)!=capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                        raise RuntimeError('cached partial queue differs')
                    if device.verified_tiles!=before:raise RuntimeError('partial queue CPU-checked as complete')
                elif result.records!=expected:raise RuntimeError('cached complete hit set differs')
                results.append({'profile':name,'case':label,'queries':count,'hits':result.total,'overflow':result.overflow})
            cache.close();cache=None;tables.close();tables=None
            print('PASS: '+name+'; six target/queue scenarios; CPU transcripts/digests, tags and guards match',flush=True)
        # Cross-product reuses each selected A tile for 32 B tiles and each B
        # tile for eight A tiles. This is an offline component experiment only.
        profile=list(cases())[1][1]
        ad=PatternDomain(profile.m,PeriodicPattern(bytes.fromhex('000103040000')))
        bd=PatternDomain(profile.n,PeriodicPattern(bytes.fromhex('000103010103')))
        queries=tuple(TileQuery(ad.indices(i*(ad.count-1)//7),bd.indices(j*(bd.count-1)//31))
                      for i in range(8)for j in range(32))
        print('Checking same-input 8 x 32 tile grid; reusable materialized cache...',flush=True)
        tables=VirtualTables(device,profile);setup=time.monotonic();cache=RowCache(tables,queries)
        setup=time.monotonic()-setup
        # Six spread-out queries have independently recomputed CPU transcripts.
        selected=tuple(queries[i]for i in (0,31,32,127,224,255))
        refs=global_reference(profile,selected)
        result=device.scan_cached(cache,selected,[MAX_BOUND]*6,6,(1<<63)+33,audit=True)
        if result.total!=6 or device.last_transcripts!=expected_transcripts(dict(zip(selected,refs)),selected):
            raise RuntimeError('grid sample differs from independent CPU')
        baseline=device.scan_wide(tables,queries,[0]*len(queries),0,(1<<63)+35,audit=True)
        old_words=device.last_transcripts
        new=device.scan_cached(cache,queries,[0]*len(queries),0,(1<<63)+35,audit=True)
        if baseline.total or new.total or device.last_transcripts!=old_words:
            raise RuntimeError('full grid transcript comparison differs')
        rounds=8;durations={}
        for label in ('virtual','cached'):
            started=time.monotonic()
            for repeat in range(rounds):
                if label=='virtual':result=device.scan_wide(tables,queries,[0]*len(queries),0,repeat)
                else:result=device.scan_cached(cache,queries,[0]*len(queries),0,repeat)
                if result.total:raise RuntimeError('unexpected all-miss timing candidate')
            durations[label]=time.monotonic()-started
        timing={'queries_per_round':len(queries),'rounds':rounds,'materialized_cache_bytes':cache.bytes,
                'materialization_seconds':setup,'virtual_seconds':durations['virtual'],
                'cached_seconds':durations['cached'],
                'cached_with_materialization_seconds':setup+durations['cached'],
                'same_input_transcripts_match':True,'independent_cpu_grid_samples':6,
                'scope':'repeated synthetic grid component times; not unique mining throughput'}
        print('PASS: full grid transcripts match; six independent CPU samples match.',flush=True)
        print('Component timings:',timing,flush=True)
    except (OSError,ValueError,RuntimeError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        if cache:cache.close()
        if tables:tables.close()
        if device:device.close()
        with os.fdopen(fd,'w')as output:
            json.dump({'complete':error is None,'gpu_checked':device is not None and error is None,
                       'cases':results,'component_timing':timing,'error':error,'submitted_shares':0,
                       'scope':'bounded offline materialized-input kernel; no pool acceptance or miner throughput claim'},output,indent=2)
            output.write('\n')
    if error:print('STOP:',error,flush=True);return 1
    print('Cached-input GPU checks complete. Existing miners, services and clocks unchanged.',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError)as exc:print('STOP:',exc,flush=True);raise SystemExit(1)
