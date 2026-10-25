#!/usr/bin/env python3
"""Independent CPU transcripts/digests versus production shared-cache GPU search. ISC."""
import argparse
import json
import os
import struct
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.native_hash import small_hash
from reference.pool_nonce import nonce_tail
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import MAX_BOUND,TileQuery
from tools.virtual_scan import VirtualTables,global_reference
from tools.production_scan import ProductionCandidateScanner
from tools.check_warp_gpu import expected_transcripts
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain


def cases():
    tail=nonce_tail(b'TESTWORK',bytes(8));a=small_hash(b'production/v027/A');b=small_hash(b'production/v027/B')
    yield 'small-boundary-tail',ConstantProfile(11,17,32768,128,64,tail,a,b),(
        TileQuery(tuple(range(10)),tuple(range(16))),
        TileQuery(tuple(range(1,11)),tuple(range(1,17)))),4096
    rows=PeriodicPattern(bytes.fromhex('000103040000'));cols=PeriodicPattern(bytes.fromhex('000103010103'))
    ad=PatternDomain(5121,rows);bd=PatternDomain(262144,cols)
    yield 'production-global-first-last',ConstantProfile(5121,262144,32768,128,64,tail,a,b),(
        TileQuery(ad.indices(0),bd.indices(0)),
        TileQuery(ad.indices(ad.count-1),bd.indices(bd.count-1))),67
    yield 'reversed-map-tail-extremes',ConstantProfile(10,16,32768,128,64,bytes([192,63])*8,
        small_hash(b'production/v027/other/A'),small_hash(b'production/v027/other/B')),(
        TileQuery(tuple(reversed(range(10))),tuple(reversed(range(16)))),),67


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    device=None;tables=None;results=[];error=None
    try:
        device=ProductionCandidateScanner();device.start(args.module)
        for name,profile,unique,count in cases():
            print('Checking '+name+' against independent CPU prefix transcripts/digests...',flush=True)
            refs=dict(zip(unique,global_reference(profile,unique)))
            queries=tuple(unique[i%len(unique)]for i in range(count))
            equal=[int.from_bytes(refs[q][1],'little')for q in queries]
            mixed=[b if i%2==0 else max(0,b-1)for i,b in enumerate(equal)]
            scenarios=[('all-hit',[MAX_BOUND]*count,count),('all-miss',[0]*count,0),
                       ('equality',equal,count),('mixed-overflow',mixed,1),('mixed-complete',mixed,count)]
            tables=VirtualTables(device,profile)
            for label,bounds,capacity in scenarios:
                expected={i:refs[q][1]for i,q in enumerate(queries)if int.from_bytes(refs[q][1],'little')<=bounds[i]}
                before=device.verified_tiles
                result=device.scan_wide(tables,queries,bounds,capacity,(1<<63)+29,audit=True)
                if result.total!=len(expected)or result.overflow!=(len(expected)>capacity):
                    raise RuntimeError('warp queue count/overflow differs')
                if expected_transcripts(refs,queries)!=device.last_transcripts:
                    raise RuntimeError('production prefix transcript differs from independent CPU')
                if result.overflow:
                    if len(result.records)!=capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                        raise RuntimeError('warp partial queue differs')
                    if device.verified_tiles!=before:raise RuntimeError('partial warp queue treated as complete')
                elif result.records!=expected:raise RuntimeError('warp complete hit set differs')
                results.append({'profile':name,'case':label,'queries':count,'hits':result.total,'overflow':result.overflow})
            tables.close();tables=None
            print(f'PASS: {name}; five target/queue cases; all transcripts/digests, tags and guards match',flush=True)
    except (OSError,ValueError,RuntimeError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        if tables:tables.close()
        if device:device.close()
        with os.fdopen(fd,'w')as output:
            json.dump({'complete':error is None,'gpu_checked':device is not None and error is None,
                       'cases':results,'error':error,'submitted_shares':0,
                       'scope':'production shared-cache kernel versus independent CPU references; no pool or throughput verdict'},output,indent=2)
            output.write('\n')
    if error:print('STOP:',error,flush=True);return 1
    print('Production shared-cache kernel checks complete. No pool connection or submission.',flush=True);return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError)as exc:print('STOP:',exc,flush=True);raise SystemExit(1)
