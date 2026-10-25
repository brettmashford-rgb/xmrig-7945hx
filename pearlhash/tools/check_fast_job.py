#!/usr/bin/env python3
"""Fresh proof plus canonical-axis production-window comparison. Offline. ISC."""
import argparse
from dataclasses import replace
import time
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.job import _HEADER_MASK,_SCRAMBLE_KEY
from pool.search import StaleWork,prepare_base,prepare_nonce,NonceSearch,build_proof,require_current
from pool.session import MiningProfile,PoolSession,MAX_U256
from reference.patterns import PeriodicPattern
from tools.offline_nonce_search import make_job
from tools.fast_plan import FastPlan,new_fast_search
from tools.prepared_dispatch import QueryPacker,PreparedDispatch,KERNELS
from tools.virtual_scan import VirtualTables
from tools.check_production_gpu import cases
from tools.production_scan import ProductionCandidateScanner
from tools.wide_scan import wide_plan_for


def synthetic_session(seed):
    p=MiningProfile(160,192,32768,128,PeriodicPattern(bytes.fromhex('000103040000')),
                    PeriodicPattern(bytes.fromhex('000103010103')))
    session=PoolSession(p,cert_version=3)
    header=make_job(seed,3).header
    payload=bytes(v^_HEADER_MASK[i]^_SCRAMBLE_KEY[i%32]for i,v in enumerate(header))+bytes(124)
    factor=p.rows.size*p.cols.size*(p.k//p.rank)*128
    target=MAX_U256//factor
    message={'id':-1,'status':1,'result':['notify',payload.hex(),
             target.to_bytes(32,'little').hex(),bytes(8).hex(),'3']}
    session.consume({'id':0,'status':1,'result':True})
    session.consume({'id':-1,'status':1,'result':['extranonce',bytes(8).hex()]})
    return session,session.consume(message),message


def production_compare(device,job):
    template=replace(job,profile=replace(job.profile,m=5121,n=262144))
    profile=list(cases())[1][1]
    old=wide_plan_for(template)
    started=time.perf_counter();fast=FastPlan.from_job(template)
    setup=time.perf_counter()-started
    packer=QueryPacker(profile);token=object();before_seconds=after_seconds=0.
    for window in range(32):
        first=window*4096;stop=first+4096
        started=time.perf_counter()
        batch=next(old.batches(first,stop))
        before=packer.prepare(token,batch.queries(),[0]*4096,4096)
        before_seconds+=time.perf_counter()-started
        started=time.perf_counter()
        batch=next(fast.batches(first,stop));after=fast.prepare(token,batch,0,4096)
        after_seconds+=time.perf_counter()-started
        if before.descriptors!=after.descriptors or before.targets!=after.targets:
            raise RuntimeError('production-window serialization differs')
    tables=None;dispatch=None
    try:
        tables=VirtualTables(device,profile);dispatch=PreparedDispatch(device,tables,KERNELS[0])
        for first in (0,fast.count//2,fast.count-4096):
            baseline=next(old.batches(first,first+4096))
            original=dispatch.prepare(baseline.queries(),[0]*4096)
            result=dispatch.run(original,38,capacity=0,audit=True);words=device.last_transcripts
            batch=next(fast.batches(first,first+4096))
            candidate=fast.prepare(dispatch.token,batch,0,4096)
            updated=dispatch.run(candidate,38,capacity=0,audit=True)
            if result.total or updated.total or words!=device.last_transcripts:
                raise RuntimeError('production-window GPU transcript differs')
    finally:
        try:
            if dispatch is not None:dispatch.close()
        finally:
            if tables is not None:tables.close()
    result={'windows':32,'queries_per_window':4096,'old_host_seconds':before_seconds,
            'new_host_seconds':after_seconds,'axis_setup_seconds':setup,
            'new_with_axis_setup_seconds':after_seconds+setup,'descriptors_match':True,
            'gpu_transcript_windows_match':3,
            'scope':'synthetic seeds; exact production row-major windows; component timing only'}
    print('PLANNING COMPARISON:',json.dumps(result),flush=True)
    print('PASS: first/middle/end production GPU transcripts match.',flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    if not os.access(args.oracle,os.X_OK):raise ValueError('existing official CPU verifier required')
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    session,job,message=synthetic_session(secrets.token_bytes(32));device=None;error=None
    report={'complete':False,'gpu_checked':False,'submitted_shares':0,'pool_connection':False,
            'scope':'fresh synthetic V3 proof through canonical-axis virtual dispatch; no pool verdict'}
    try:
        print('Preparing fresh 160x192 K32768 V3 job for the reusable search path...',flush=True)
        base=prepare_base(job,session.is_current)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        with new_fast_search(context,device,session.is_current)as search:
            hit,cursor=search.advance(1)
            if hit is None:raise RuntimeError('near-maximum synthetic bound produced no candidate')
            proof_hit=hit
            raw,_=build_proof(context,proof_hit,session.is_current)
            report['proof_tiles_scanned']=cursor.next_tile
        proof_path=args.output_dir/'prepared-job-proof-v3.json'
        proof_path.write_text(json.dumps({'cert_version':3,
            'header_base64':base64.b64encode(job.header).decode(),
            'plain_proof_base64':base64.b64encode(raw).decode(),'share_nbits':None})+'\n')
        subprocess.run([str(args.oracle.resolve()),'verify',str(proof_path.resolve())],check=True,
                       timeout=120,env=dict(os.environ,RAYON_NUM_THREADS='2'))
        print('PASS: fresh job -> nonce -> reusable GPU candidate -> new V3 proof -> official CPU verifier.',flush=True)
        report['official_cpu_verifier']='passed'
        # Distinct target generation, fresh nonce, two resumable miss windows.
        message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
        context2=prepare_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        search=new_fast_search(context2,device,session.is_current)
        try:
            allocations=tuple(id(p)for p in search.backend.dispatch.owned)
            for _ in range(2):
                hit,cursor=search.advance(8)
                if hit is not None:raise RuntimeError('unexpected tiny-bound synthetic candidate')
                if tuple(id(p)for p in search.backend.dispatch.owned)!=allocations:
                    raise RuntimeError('resumable window reallocated dispatch buffers')
            if cursor.next_tile!=16 or search.backend.preparations!=2:
                raise RuntimeError('resumable cursor or batch preparation differs')
            report['miss_windows']=2;report['miss_tiles']=cursor.next_tile
            session.consume(message)
            try:search.advance(1)
            except StaleWork:pass
            else:raise RuntimeError('stale search resumed')
            if not search.closed or not search.backend.closed:
                raise RuntimeError('stale search retained nonce buffers')
            report['stale_search_rejected']=True
        finally:search.close()
        try:build_proof(context,proof_hit,session.is_current)
        except StaleWork:report['stale_proof_rejected']=True
        else:raise RuntimeError('stale proof entered construction')
        print('PASS: two windows retain dispatch buffers; replacement rejects and closes stale search/proof.',flush=True)
        report['production_comparison']=production_compare(device,job)
        report['complete']=True;report['gpu_checked']=True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        session.close()
        if device is not None:
            try:device.close()
            except Exception as exc:error=error or str(exc)
        report['error']=error;report['complete']=report['complete']and error is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if error:print('STOP:',error,flush=True);return 1
    print('Fresh canonical-axis search checks complete. No pool connection or share sent.',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
