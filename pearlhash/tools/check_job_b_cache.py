#!/usr/bin/env python3
"""Reused B tables: production transcript equality, independent CPU checks and fresh V3 proofs. ISC."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import ctypes as C
import struct
import time
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_search_loops import production_session
from tools.check_prepared_job import synthetic_session
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.shared_b_scan import new_shared_b_search,canonical_tile,RowPairQueries
from tools.job_b_tables import JobBTables,new_job_b_search
from tools.fast_plan import FastBatch
from tools.virtual_scan import global_reference
from tools.production_scan import ProductionCandidateScanner
from pool.search import prepare_nonce,build_proof,StaleWork


def audit_context(context,device,current,owner,report):
    old=new=None
    try:
        started=time.perf_counter();old=new_shared_b_search(context,device,current)
        report['setup_seconds']['fresh-B'].append(time.perf_counter()-started)
        started=time.perf_counter();new=new_job_b_search(context,device,current,owner)
        report['setup_seconds']['job-B'].append(time.perf_counter()-started)
        for first in (1,new.plan.count-4096):
            a=FastBatch(old.plan,first,first+4096);b=FastBatch(new.plan,first,first+4096)
            old.backend.dispatch.scan_window(a,old.backend.dispatch.prepare_window(a),context.job.generation,capacity=0,audit=True)
            expected=device.last_transcripts
            new.backend.dispatch.scan_window(b,new.backend.dispatch.prepare_window(b),context.job.generation,capacity=0,audit=True)
            if device.last_transcripts!=expected:raise RuntimeError('reused B production transcript differs from fresh B')
            for index in (0,4095):
                transcript,_=global_reference(context.profile,(RowPairQueries(b)[index],))[0]
                if expected[index]!=struct.unpack('<16I',transcript):raise RuntimeError('reused B independent CPU transcript differs')
                report['cpu_samples']+=1
            report['transcript_windows']+=1
            print('Reused B production transcript window',report['transcript_windows'],'/4 checked.',flush=True)
    finally:
        if new is not None:new.close()
        if old is not None:old.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,
        production_contexts_checked=0,proof_contexts_checked=0,official_cpu_verifiers=0,
        gpu_scanner='shared-B-v060',nonce_cache_reused=False,b_tables_reused=False,
        transcript_windows=0,cpu_samples=0,guard_cases=0,setup_seconds={'fresh-B':[],'job-B':[]})
    session=device=owner=None
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
            if index<2:
                if device is None:
                    device=ProductionCandidateScanner();device.start(args.module)
                    owner=JobBTables(device,new,session.is_current)
                audit_context(new,device,session.is_current,owner,report)
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
        if owner.leases!=2:raise RuntimeError('production B tables were not reused twice')
        report['production_b_table_builds']=1;report['production_b_table_leases']=owner.leases
        owner.close();owner=None
        if device.allocations:raise RuntimeError('production B reuse leaked allocations')
        device.close();device=None
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
            if owner is None:owner=JobBTables(device,context,session.is_current)
            with new_job_b_search(context,device,session.is_current,owner,start=1)as search:
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
        report['nonce_cache_reused']=True;report['b_tables_reused']=owner.leases==2
        message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
        context=prepare_cached_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,cache)
        with new_job_b_search(context,device,session.is_current,owner)as search:
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
        # A stale search releases its lease, while shared B allocations remain.
        if owner.leased:raise RuntimeError('stale search kept its B lease')
        # Restore a current generation and inject every retained guard endpoint.
        fresh=session.consume(message)
        context=prepare_cached_nonce(fresh,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,cache)
        for index in range(28):
            search=new_job_b_search(context,device,session.is_current,owner)
            dispatch=search.backend.dispatch;address=C.c_ulonglong(dispatch.guard_addresses[index])
            try:
                dispatch.upload(address,bytes(16))
                try:search.advance(1)
                except RuntimeError as error:
                    if 'guard'not in str(error):raise
                else:raise RuntimeError('reused B dispatch accepted corrupted guard')
                report['guard_cases']+=1
            finally:
                # B guard storage belongs to owner, so restore before next lease.
                raw=C.create_string_buffer(b'\xa5'*16,16)
                # A/dispatch allocations may already be gone after fatal cleanup.
                if address.value in (owner.buffer[0].value,owner.buffer[0].value+owner.buffer[4]*128+16,
                        owner.buffer[2].value,owner.buffer[2].value+context.profile.k*4+16):
                    device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],address,raw,16)
                search.close()
        owner.close();owner=None
        if device.allocations:raise RuntimeError('cached nonce/B-table proof leaked GPU allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as error:
        report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        if owner is not None:
            try:owner.close()
            except Exception as error:report['error']=report['error']or('B cleanup: '+str(error))
        if device is not None:
            try:device.close()
            except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('JOB B CACHE PREFLIGHT:',json.dumps(report),flush=True)
    return 0 if report['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
