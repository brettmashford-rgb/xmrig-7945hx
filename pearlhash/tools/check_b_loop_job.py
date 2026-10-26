#!/usr/bin/env python3
"""Grouped and early-prepared quad5 loops versus validated quad5, fresh proofs and guard faults. ISC."""
import argparse
import ctypes as C
import base64
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
from types import SimpleNamespace
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_search_loops import production_session
from tools.check_prepared_job import synthetic_session
from tools.check_production_gpu import cases
from tools.production_scan import ProductionCandidateScanner
from tools.virtual_scan import VirtualTables,global_reference
from tools.cached_a import CachedA
from tools.b_quad_scan import BQuadPaddedDispatch,kernel_resources
from tools.b_loop_scan import BGroupedDispatch,BEarlyDispatch,new_b_loop_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_tile_scan_gpu import MAX_BOUND
from tools.gpu_base import prepare_gpu_base
from pool.search import prepare_nonce,build_proof,StaleWork


def check_mode(args,direct):
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    dispatch_type=BEarlyDispatch if direct else BGroupedDispatch
    report={'complete':False,'error':None,'pool_connection':False,'submitted_shares':0,'target_cases':0,'transcript_windows':0,'cpu_samples':0,'guard_cases':0}
    device=tables=cache=old=new=session=None
    def clear():
        nonlocal tables,cache,old,new
        for resource in (new,old,cache,tables):
            if resource is not None:resource.close()
        new=old=cache=tables=None
    try:
        session,job=production_session();plan=FastPlan.from_job(job);profile=list(cases())[1][1]
        device=ProductionCandidateScanner();device.start(args.module)
        tables=VirtualTables(device,profile);cache=CachedA(tables)
        old=BQuadPaddedDispatch(device,tables,cache,plan,0)
        new=dispatch_type(device,tables,cache,plan,0)
        report['kernel_resources']={'baseline':kernel_resources(old),'candidate':kernel_resources(new)}
        for first in (0,len(plan.cols)-33,plan.count//2,plan.count-4096):
            batch=FastBatch(plan,first,first+4096)
            original=old.scan_window(batch,old.prepare_window(batch),(1<<63)+47,capacity=0,audit=True);words=device.last_transcripts
            updated=new.scan_window(batch,new.prepare_window(batch),(1<<63)+47,capacity=0,audit=True)
            if original.total or updated.total or device.last_transcripts!=words:
                raise RuntimeError('packed resident transcripts differ from canonical CPU/quad5-v052')
            for index in (0,4095):
                transcript,_=global_reference(profile,(batch.queries()[index],))[0]
                if words[index]!=struct.unpack('<16I',transcript):raise RuntimeError('independent CPU transcript differs')
                report['cpu_samples']+=1
            report['transcript_windows']+=1
            print('Transcript window',str(report['transcript_windows'])+'/4 checked.',flush=True)
        print('PASS: four full B-loop transcript windows (first, row crossing, middle, end); eight CPU samples.',flush=True)
        for first in (0,plan.count//2,plan.count-1):
            batch=FastBatch(plan,first,first+1);query=batch.queries()[0]
            transcript,digest=global_reference(profile,(query,))[0];equal=int.from_bytes(digest,'little')
            for label,bound,capacity in (('hit',MAX_BOUND,1),('miss',0,1),('equal',equal,1),
                    ('below',max(0,equal-1),1),('overflow',MAX_BOUND,0),('zero-miss',0,0)):
                new.bound=bound;new.upload(new.targets[1],bound.to_bytes(32,'little')*4096)
                before=device.verified_tiles
                result=new.scan_window(batch,new.prepare_window(batch),(1<<63)+45,capacity=capacity,audit=True)
                expected=int(equal<=bound)
                if (result.total!=expected or result.overflow!=(expected>capacity)
                        or device.last_transcripts!=(struct.unpack('<16I',transcript),)):
                    raise RuntimeError('resident single target/queue differs from CPU')
                if not result.overflow and result.records!=({0:digest}if expected else{}):raise RuntimeError('resident hit differs')
                if result.overflow and device.verified_tiles!=before:raise RuntimeError('partial resident queue credited')
                report['target_cases']+=1
        # Nonzero-capacity partial queue, validating its returned record independently.
        new.bound=MAX_BOUND;new.upload(new.targets[1],MAX_BOUND.to_bytes(32,'little')*4096)
        batch=FastBatch(plan,plan.count-67,plan.count);before=device.verified_tiles
        result=new.scan_window(batch,new.prepare_window(batch),(1<<63)+45,capacity=1)
        if result.total!=67 or not result.overflow or len(result.records)!=1 or device.verified_tiles!=before:
            raise RuntimeError('resident partial queue overflow differs')
        for index,digest in result.records.items():
            if global_reference(profile,(batch.queries()[index],))[0][1]!=digest:raise RuntimeError('partial resident record differs')
        report['partial_queue_checked']=True
        print('PASS: eighteen CPU target/queue cases plus populated partial queue.',flush=True)
        new.close();new=None
        # Each corruption is fatal to that dispatch. Recreate after restoring
        # the sentinel; never resume a failed search or alter payload bytes.
        for guard_index in range(28):
            new=dispatch_type(device,tables,cache,plan,0)
            address=C.c_ulonglong(new.guard_addresses[guard_index])
            try:
                new.upload(address,bytes(16))
                batch=FastBatch(plan,0,1)
                try:new.scan_window(batch,new.prepare_window(batch),47,capacity=0)
                except RuntimeError as exc:
                    if 'guard' not in str(exc):raise
                else:raise RuntimeError('corrupted guard accepted')
                report['guard_cases']+=1
            finally:
                new.upload(address,b'\xa5'*16);new.close();new=None
        print('PASS: all 28 guard endpoints reject deliberate corruption.',flush=True)
        clear();device.close();device=None;session.close()
        print('Preparing fresh B-loop candidate and V3 proof for the official CPU verifier.',flush=True)
        session,job,message=synthetic_session(secrets.token_bytes(32))
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        with new_b_loop_search(context,device,session.is_current,variant='early' if direct else 'grouped')as search:
            hit,cursor=search.advance(1)
            if hit is None:raise RuntimeError('fresh resident proof candidate absent')
            proof,_=build_proof(context,hit,session.is_current)
        path=args.output_dir/'b-loop-proof-v3.json'
        path.write_text(json.dumps({'cert_version':3,'header_base64':base64.b64encode(job.header).decode(),
            'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None})+'\n')
        subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,
                       env=dict(os.environ,RAYON_NUM_THREADS='2'))
        report['official_cpu_verifier']='passed'
        # A new tiny-target nonce must retain buffers across odd miss windows.
        message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
        context=prepare_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        with new_b_loop_search(context,device,session.is_current,variant='early' if direct else 'grouped')as search:
            owned=tuple(p.value for p in search.backend.dispatch.owned)
            for amount in (5,7):
                hit,cursor=search.advance(amount)
                if hit is not None or owned!=tuple(p.value for p in search.backend.dispatch.owned):
                    raise RuntimeError('resident miss windows or retained allocations differ')
            if cursor.next_tile!=12:raise RuntimeError('resident resumable cursor differs')
            session.consume(message)
            try:search.advance(1)
            except StaleWork:pass
            else:raise RuntimeError('stale resident search resumed')
            if not search.closed:raise RuntimeError('stale resident search remained open')
        report['retained_windows_and_stale_rejected']=True
        if device.allocations:raise RuntimeError('resident checks leaked device allocations')
        report['complete']=True;print('PASS: fresh resident V3 proof verified; retained windows and stale search rejected.',flush=True)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if session is not None:session.close()
        for resource in (new,old,cache,tables,device):
            if resource is not None:
                try:resource.close()
                except Exception as exc:report['error']=report['error']or('cleanup: '+str(exc))
        report['complete']=report['complete']and report['error']is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['error']:print('STOP:',report['error'],flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    reports=[]
    for direct,label in ((False,'grouped'),(True,'early')):
        print('Checking',label,'scan path.',flush=True)
        report=check_mode(SimpleNamespace(module=args.module,commitment_module=args.commitment_module,
            oracle=args.oracle,output_dir=args.output_dir/label),direct)
        reports.append(report)
        if not report['complete']:break
    complete=len(reports)==2 and all(r['complete'] for r in reports)
    result=dict(complete=complete,error=next((r['error']for r in reports if r['error']),None),
        pool_connection=False,submitted_shares=0,modes_checked=len(reports),
        transcript_windows=sum(r['transcript_windows']for r in reports),
        cpu_samples=sum(r['cpu_samples']for r in reports),target_cases=sum(r['target_cases']for r in reports),
        guard_cases=sum(r['guard_cases']for r in reports),
        partial_queue_checked=all(r.get('partial_queue_checked')is True for r in reports),
        official_cpu_verifiers=sum(r.get('official_cpu_verifier')=='passed'for r in reports),
        retained_windows_and_stale_rejected=all(r.get('retained_windows_and_stale_rejected')is True for r in reports))
    (args.output_dir/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('LOOP PREFLIGHT:',json.dumps(result),flush=True)
    return 0 if complete else 1


if __name__=='__main__':raise SystemExit(main())
