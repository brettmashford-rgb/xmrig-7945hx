#!/usr/bin/env python3
"""Virtual fragment/cache correctness and a fresh V3 offline proof. No pool IO."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern
from reference.pool_nonce import nonce_tail
from reference.tile_ranges import PatternDomain,RangePlan
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import MAX_BOUND,TileQuery
from tools.virtual_scan import VirtualScanner,VirtualTables,VirtualRangeBackend,global_reference,table_payload
from tools.offline_nonce_search import make_job,prepare_base,prepare_nonce,find_candidate,build_candidate


def cases():
    a=small_hash(b'pearlhash/virtual/v017/A');b=small_hash(b'pearlhash/virtual/v017/B')
    tail=nonce_tail(bytes(range(8)),bytes(range(8,16)))
    p=ConstantProfile(32,32,1056,32,64,tail,a,b)
    q=[TileQuery(tuple(range(32)),tuple(range(32))),
       TileQuery(tuple(range(16,-1,-1)),tuple(range(8,-1,-1))),
       TileQuery((31,),(31,)),TileQuery((0,0,31),(0,31,0))]
    yield 'eight-warps-rank32',p,q
    p=ConstantProfile(3,4,2048,1024,-64,tail,a,b)
    q=[TileQuery((0,1,2),(0,1,2,3)),TileQuery((2,),(3,)),TileQuery((2,0,2),(3,1,3))]
    yield 'negative-fill-rank1024',p,q
    p=ConstantProfile(5121,262144,32768,128,64,tail,a,b)
    rows=PeriodicPattern.from_list([0,1,8,9,16,17,24,25,32,33])
    cols=PeriodicPattern.from_list([0,1,8,9,32,33,40,41,64,65,72,73,96,97,104,105])
    plan=RangePlan(PatternDomain(p.m,rows),PatternDomain(p.n,cols));q=[]
    for start in (0,plan.count//2,plan.count-2):
        for tile in (start,start+1):q.append(TileQuery(*plan.indices(tile)))
    q.append(TileQuery((p.m-1,),(p.n-1,))) # Directly exercise the nonce tail too.
    yield 'production-shaped-cache',p,q


def check_case(device,name,profile,queries):
    payload=table_payload(profile);reference=global_reference(profile,queries)
    if device is None:
        print(f'CPU-ONLY: {name}: {len(queries)} scalar tile references prepared; GPU not run',flush=True)
        return {'name':name,'table_payload_bytes':payload,'queries':len(queries),'gpu_checked':False}
    tables=VirtualTables(device,profile)
    try:
        probed=device.probe(tables);digests=[int.from_bytes(d,'little')for _,d in reference];n=len(queries)
        scenarios=([MAX_BOUND]*n,[max(0,d-1)for d in digests],digests,
                   [MAX_BOUND if i%2 else 0 for i in range(n)],[MAX_BOUND]*n,[MAX_BOUND]*n)
        for index,bounds in enumerate(scenarios):
            capacity=n if index<4 else (1 if index==4 else 0)
            result=device.scan_virtual(tables,queries,reference,bounds,capacity,0x1700000000000000+index,audit=True)
            if result.overflow:
                try:result.require_complete()
                except RuntimeError:pass
                else:raise RuntimeError('virtual queue overflow was silently accepted')
            else:result.require_complete()
        print(f'PASS: {name}: {probed} virtual signed-byte probes; {n} tiles x 6 target/queue checks; '
              'tables, transcripts, digests, tags and guards match',flush=True)
        return {'name':name,'table_payload_bytes':payload,'queries':n,'gpu_checked':True,'probed_bytes':probed}
    finally:tables.close()


def materialized_regression(device):
    # The common scan body was refactored; check one small original-wrapper case.
    profile=next(cases())[1]
    from reference.tile_ranges import RangeBatch
    from tools.check_tile_scan_gpu import query_reference
    rows=tuple(range(32));cols=tuple(range(32));maps=((rows,cols),)
    batch=RangeBatch(0,1,rows,cols,maps);case=profile.case(batch);matrix=case.matrix()
    queries=[TileQuery(*maps[0])];reference=query_reference(matrix,queries)
    mark=len(device.allocations)
    try:
        a,key=device.generate_side(case,case.sides()[0],matrix.a)
        b,_=device.generate_side(case,case.sides()[1],matrix.bt)
        device.scan(matrix,queries,reference,a,b,key,[MAX_BOUND],1,17,audit=True).require_complete()
        print('PASS: refactored materialized-wrapper regression matches CPU reference',flush=True)
    finally:
        for pointer in reversed(device.allocations[mark:]):device.release(pointer)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module','--cubin',dest='module',type=Path,default=BASE/'gpu/tile-scan-sm120.ptx')
    parser.add_argument('--oracle',type=Path,help='existing official CPU oracle')
    parser.add_argument('--output-dir',type=Path,required=True,help='new local run directory')
    parser.add_argument('--cpu-only',action='store_true')
    args=parser.parse_args();oracle=args.oracle.resolve()if args.oracle else None
    if (not args.cpu_only and oracle is None)or (oracle and (not oracle.is_file()or not os.access(oracle,os.X_OK))):
        raise ValueError('existing official oracle executable is required')
    if args.output_dir.exists():raise ValueError('output directory already exists')
    args.output_dir.mkdir(parents=True,exist_ok=False);out=args.output_dir.resolve()
    device=None;checks=[]
    try:
        if not args.cpu_only:device=VirtualScanner();device.start(args.module)
        for name,profile,queries in cases():
            print(f'Checking {name}; full noise-table payload {table_payload(profile)} bytes...',flush=True)
            checks.append(check_case(device,name,profile,queries))
        if device:materialized_regression(device)
        seed=secrets.token_bytes(32);job=make_job(seed,3);base=prepare_base(job)
        worker=secrets.token_bytes(8);found=None
        print('Checking a fresh V3 nonce/proof through the virtual GPU input path...',flush=True)
        for attempt in range(3):
            context=prepare_nonce(job,base,worker,secrets.token_bytes(8),17+attempt)
            found,cursor=find_candidate(context,device,backend_factory=VirtualRangeBackend)
            if found:break
        if found is None:raise RuntimeError('bounded synthetic nonce attempts found no candidate')
        proof,_=build_candidate(context,found)
        value={'cert_version':3,'header_base64':base64.b64encode(job.header).decode(),
               'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None,
               'provenance':{'scope':'fresh synthetic virtual-input proof; not a pool verdict',
                             'synthetic_seed_hex':seed.hex(),'worker_nonce':context.worker.hex(),
                             'miner_nonce':context.miner.hex(),'generation':context.generation,'tile_id':found.tile}}
        path=out/'virtual-proof-v3.json';path.write_text(json.dumps(value,indent=2)+'\n')
        if device and device.allocations:raise RuntimeError('virtual test allocations were not released')
        if oracle:
            subprocess.run([str(oracle),'verify',str(path)],check=True,timeout=120,env=dict(os.environ,RAYON_NUM_THREADS='2'))
            print('PASS: fresh virtual-input V3 proof accepted by official offline CPU verifier',flush=True)
        else:print('CPU-ONLY: V3 proof prepared; GPU and official verification NOT RUN',flush=True)
    finally:
        if device:device.close()
    manifest={'complete':True,'gpu_checked':not args.cpu_only,'checks':checks,
              'official_cpu_verifier':'passed'if oracle else 'not run',
              'materialized_wrapper_regression_checked':not args.cpu_only,
              'scope':'virtual fragment/cache correctness + fresh synthetic V3 proof; no full production nonce, pool submission or performance claim'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    mode='CPU-only preparation; GPU NOT RUN'if args.cpu_only else 'GPU noise tables/fragments/tile scan checked'
    print(f'Offline virtual-input checks complete. CPU commitments/seeds/proof; {mode}. No pool submission or performance claim.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as error:
        print('FAIL:',error);raise SystemExit(1)
