#!/usr/bin/env python3
"""Fresh job->nonce->reusable GPU search->proof->official verifier. Offline. ISC."""
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
from pool.job import _HEADER_MASK,_SCRAMBLE_KEY
from pool.search import StaleWork,prepare_base,prepare_nonce,NonceSearch,build_proof,require_current
from pool.session import MiningProfile,PoolSession,MAX_U256
from reference.patterns import PeriodicPattern
from tools.offline_nonce_search import make_job
from tools.prepared_backend import PreparedCandidateBackend
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


def backend_for(job,current):
    def generation():
        require_current(job,current);return job.generation
    def factory(profile,device,*,bound):
        return PreparedCandidateBackend(profile,device,bound=bound,current_generation=generation)
    return factory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    if not os.access(args.oracle,os.X_OK):raise ValueError('existing official CPU verifier required')
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    session,job,message=synthetic_session(secrets.token_bytes(32));device=None;error=None
    report={'complete':False,'gpu_checked':False,'submitted_shares':0,'pool_connection':False,
            'scope':'fresh synthetic V3 proof through reusable virtual dispatch; no pool verdict'}
    try:
        print('Preparing fresh 160x192 K32768 V3 job for the reusable search path...',flush=True)
        base=prepare_base(job,session.is_current)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        with NonceSearch(context,device,session.is_current,backend_factory=backend_for(job,session.is_current),
                         plan_factory=wide_plan_for)as search:
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
        search=NonceSearch(context2,device,session.is_current,backend_factory=backend_for(small,session.is_current),
                           plan_factory=wide_plan_for)
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
    print('Fresh reusable-search proof checks complete. No pool connection or share sent.',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
