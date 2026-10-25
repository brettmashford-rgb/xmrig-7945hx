#!/usr/bin/env python3
"""Cached A / virtual B correctness and exact-window comparison. Offline. ISC."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.session import MiningProfile
from pool.search import prepare_nonce,build_proof
from reference.patterns import PeriodicPattern
from tools.cached_a import CachedA,attach,new_cached_a_search
from tools.check_prepared_job import synthetic_session
from tools.check_production_gpu import cases
from tools.check_warp_gpu import expected_transcripts
from tools.check_tile_scan_gpu import MAX_BOUND
from tools.fast_plan import FastPlan
from tools.gpu_base import prepare_gpu_base
from tools.prepared_dispatch import PreparedDispatch,KERNELS
from tools.production_scan import ProductionCandidateScanner
from tools.virtual_scan import VirtualTables,global_reference


def preferred(old_seconds,new_seconds,setup_seconds):
    if any(type(v)not in(int,float)or v<0 for v in(old_seconds,new_seconds,setup_seconds)):
        raise ValueError('invalid comparison durations')
    return 'cached-a'if new_seconds+setup_seconds<old_seconds*.97 else 'baseline'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--commitment-module',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if not os.access(args.oracle,os.X_OK):raise ValueError('existing official verifier required')
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    device=tables=cache=old=new=session=None;error=None
    report={'complete':False,'gpu_checked':False,'cases':[],'submitted_shares':0,'pool_connection':False,
            'scope':'offline cached-A correctness and component comparison; no live throughput claim'}
    def close_buffers():
        nonlocal tables,cache,old,new
        for resource in (old,new,cache,tables):
            if resource is not None:resource.close()
        old=new=cache=tables=None
    try:
        device=ProductionCandidateScanner();device.start(args.module)
        for name,profile,unique,count in cases():
            print('Checking cached A / virtual B:',name,flush=True)
            refs=dict(zip(unique,global_reference(profile,unique)));queries=tuple(unique[i%len(unique)]for i in range(count))
            tables=VirtualTables(device,profile);cache=CachedA(tables)
            new=PreparedDispatch(device,tables,KERNELS[0]);attach(new,cache)
            equal=[int.from_bytes(refs[q][1],'little')for q in queries]
            mixed=[v if i%2==0 else max(0,v-1)for i,v in enumerate(equal)]
            scenarios=(('hit',[MAX_BOUND]*count,count),('miss',[0]*count,0),('equality',equal,count),
                       ('zero-queue',[MAX_BOUND]*count,0),('overflow',mixed,1),('mixed',mixed,count))
            for label,bounds,capacity in scenarios:
                before=device.verified_tiles;batch=new.prepare(queries,bounds)
                result=new.run(batch,(1<<63)+40,capacity=capacity,audit=True)
                expected={i:refs[q][1]for i,q in enumerate(queries)if int.from_bytes(refs[q][1],'little')<=bounds[i]}
                if (result.total!=len(expected)or result.overflow!=(len(expected)>capacity)
                        or device.last_transcripts!=expected_transcripts(refs,queries)):
                    raise RuntimeError('cached-A target/queue/transcript differs from independent CPU')
                if result.overflow:
                    if len(result.records)!=capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                        raise RuntimeError('cached-A partial queue differs')
                    if before!=device.verified_tiles:raise RuntimeError('partial queue credited as verified')
                elif result.records!=expected:raise RuntimeError('cached-A complete hits differ')
                report['cases'].append({'profile':name,'case':label,'passed':True})
            close_buffers()
            print('PASS:',name,'six independent CPU transcript/target/queue cases.',flush=True)
        profile=list(cases())[1][1]
        job=SimpleNamespace(profile=MiningProfile(profile.m,profile.n,32768,128,
            PeriodicPattern(bytes.fromhex('000103040000')),PeriodicPattern(bytes.fromhex('000103010103'))))
        plan=FastPlan.from_job(job);tables=VirtualTables(device,profile);cache=CachedA(tables)
        old=PreparedDispatch(device,tables,KERNELS[0]);new=PreparedDispatch(device,tables,KERNELS[0]);attach(new,cache)
        for first in (0,plan.count//2,plan.count-4096):
            batch=next(plan.batches(first,first+4096))
            a=plan.prepare(old.token,batch,0,4096);b=plan.prepare(new.token,batch,0,4096)
            result=old.run(a,40,capacity=0,audit=True);words=device.last_transcripts
            updated=new.run(b,40,capacity=0,audit=True)
            if result.total or updated.total or device.last_transcripts!=words:
                raise RuntimeError('production cached-A GPU transcripts differ')
        print('PASS: first/middle/end production GPU transcripts match.',flush=True)
        durations={'baseline':[],'cached-a':[]}
        for window in range(16):
            first=(window%8)*4096+(plan.count//2 if window>=8 else 0)
            batch=next(plan.batches(first,first+4096))
            prepared={'baseline':(old,plan.prepare(old.token,batch,0,4096)),
                      'cached-a':(new,plan.prepare(new.token,batch,0,4096))}
            order=('baseline','cached-a')if window%2==0 else('cached-a','baseline')
            for label in order:
                dispatch,source=prepared[label];started=time.perf_counter()
                result=dispatch.run(source,window,capacity=0)
                durations[label].append(time.perf_counter()-started)
                if result.total or result.overflow:raise RuntimeError('unexpected timing candidate')
        a=sum(durations['baseline']);b=sum(durations['cached-a']);setup=cache.setup_seconds
        report['scan_comparison']={'windows':16,'queries_per_window':4096,'baseline_seconds':a,
            'cached_a_seconds':b,'a_cache_setup_seconds':setup,'cached_a_with_setup_seconds':b+setup,
            'a_cache_bytes':cache.bytes,'preferred':preferred(a,b,setup),'round_seconds':durations,
            'scope':'same production row-major windows; alternating order; component times only'}
        print('SCAN COMPARISON:',json.dumps(report['scan_comparison']),flush=True)
        close_buffers();device.close();device=None
        session,job,message=synthetic_session(secrets.token_bytes(32))
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        with new_cached_a_search(context,device,session.is_current)as search:
            hit,cursor=search.advance(1)
            if hit is None:raise RuntimeError('near-maximum synthetic bound produced no candidate')
            proof,_=build_proof(context,hit,session.is_current)
        path=args.output_dir/'cached-a-proof-v3.json'
        path.write_text(json.dumps({'cert_version':3,'header_base64':base64.b64encode(job.header).decode(),
            'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None})+'\n')
        subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,
                       env=dict(os.environ,RAYON_NUM_THREADS='2'))
        report['official_cpu_verifier']='passed';report['complete']=True;report['gpu_checked']=True
        print('PASS: fresh cached-A V3 proof accepted by official offline CPU verifier.',flush=True)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        if session is not None:session.close()
        for resource in (old,new,cache,tables,device):
            if resource is not None:
                try:resource.close()
                except Exception as exc:error=error or('cleanup: '+str(exc))
        report['error']=error;report['complete']=report['complete']and error is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if error:print('STOP:',error,flush=True);return 1
    print('Cached-A preflight complete. No pool connection or share sent.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
