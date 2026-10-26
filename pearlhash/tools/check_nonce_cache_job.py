#!/usr/bin/env python3
"""Full-tree nonce equality plus two cached-nonce v60 candidates/V3 official proofs. ISC."""
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
from tools.compare_search_loops import production_session
from tools.check_prepared_job import synthetic_session
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.shared_b_scan import new_shared_b_search,canonical_tile
from tools.production_scan import ProductionCandidateScanner
from pool.search import prepare_nonce,build_proof,StaleWork


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,
        production_contexts_checked=0,proof_contexts_checked=0,official_cpu_verifiers=0,
        gpu_scanner='shared-B-v060',nonce_cache_reused=False)
    session=device=None
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        print('Building one verified production A frontier; then checking four full-tree nonce contexts.',flush=True)
        cache=NonceCommitmentCache.build(job,session.is_current)
        if cache.total_leaves!=163872 or len(cache.siblings)!=7:raise RuntimeError('production frontier shape differs')
        report['production_leaves']=cache.total_leaves;report['production_parent_hashes']=len(cache.siblings)
        for index in range(4):
            miner=secrets.token_bytes(8)
            old=prepare_nonce(job,base,b'TESTWORK',miner,session.is_current)
            new=prepare_cached_nonce(job,base,b'TESTWORK',miner,session.is_current,cache)
            if old!=new:raise RuntimeError('cached production nonce root/seeds/tail differ from full tree')
            report['production_contexts_checked']+=1
            print('Production nonce equality',str(index+1)+'/4 passed.',flush=True)
        for current in (lambda candidate:False,):
            try:prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),current,cache)
            except StaleWork:pass
            else:raise RuntimeError('stale cached nonce accepted')
        checks=[0]
        def stale_after_root(candidate):
            checks[0]+=1;return checks[0]==1
        try:prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),stale_after_root,cache)
        except StaleWork:pass
        else:raise RuntimeError('generation change after cached root accepted')
        report['stale_preparation_rejected']=True
        session.close();session,job,message=synthetic_session(secrets.token_bytes(32))
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        cache=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        for index in range(2):
            miner=secrets.token_bytes(8)
            context=prepare_cached_nonce(job,base,b'TESTWORK',miner,session.is_current,cache)
            if context!=prepare_nonce(job,base,b'TESTWORK',miner,session.is_current):
                raise RuntimeError('cached proof nonce context differs')
            report['proof_contexts_checked']+=1
            with new_shared_b_search(context,device,session.is_current,shared=True,start=1)as search:
                hit,cursor=search.advance(1)
                if hit is None or hit.tile!=canonical_tile(search.plan,1):raise RuntimeError('fresh canonical cached-nonce hit absent')
                proof,_=build_proof(context,hit,session.is_current)
            path=args.output_dir/('cached-nonce-proof-'+str(index+1)+'.json')
            path.write_text(json.dumps({'cert_version':3,'header_base64':base64.b64encode(job.header).decode(),
                'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None})+'\n')
            subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,
                env=dict(os.environ,RAYON_NUM_THREADS='2'))
            report['official_cpu_verifiers']+=1
            print('PASS: cached nonce',index+1,'-> unchanged v60 scanner -> fresh V3 proof -> official CPU verifier.',flush=True)
        report['nonce_cache_reused']=True
        message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
        context=prepare_cached_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,cache)
        with new_shared_b_search(context,device,session.is_current,shared=True)as search:
            owned=tuple(p.value for p in search.backend.dispatch.owned)
            for amount in (5,7):
                hit,cursor=search.advance(amount)
                if hit is not None or owned!=tuple(p.value for p in search.backend.dispatch.owned):
                    raise RuntimeError('cached nonce retained miss window differs')
            if cursor.next_tile!=12:raise RuntimeError('cached nonce cursor differs')
            session.consume(message)
            try:search.advance(1)
            except StaleWork:pass
            else:raise RuntimeError('stale cached nonce scan resumed')
            if not search.closed:raise RuntimeError('stale cached nonce scan remained open')
        report['retained_windows_and_stale_rejected']=True
        if device.allocations:raise RuntimeError('cached nonce proof leaked GPU allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as error:
        report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        if device is not None:
            try:device.close()
            except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('NONCE CACHE PREFLIGHT:',json.dumps(report),flush=True)
    return 0 if report['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
