#!/usr/bin/env python3
"""Fresh dual-stream candidate/proof and stale-pair lifecycle gate. Offline. ISC."""
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
from pool.search import prepare_nonce,build_proof,StaleWork
from tools.check_prepared_job import synthetic_session
from tools.gpu_base import prepare_gpu_base
from tools.dual_search import DualSearch
from tools.production_scan import ProductionCandidateScanner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    session,job,message=synthetic_session(secrets.token_bytes(32));device=None;search=None
    report={'complete':False,'error':None,'pool_connection':False,'submitted_shares':0}
    try:
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        with DualSearch(context,device,session.is_current)as search:
            hit,cursor=search.advance(2)
            if hit is None or cursor.next_tile!=2 or search.backend.dispatches!=2:
                raise RuntimeError('fresh paired candidate/cursor differs')
            proof_hit=hit;proof,_=build_proof(context,hit,session.is_current)
        path=args.output_dir/'dual-proof-v3.json'
        path.write_text(json.dumps({'cert_version':3,'header_base64':base64.b64encode(job.header).decode(),
            'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None})+'\n')
        subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,
                       env=dict(os.environ,RAYON_NUM_THREADS='2'))
        report['official_cpu_verifier']='passed'
        print('PASS: fresh two-stream candidate -> new V3 proof -> official offline CPU verifier.',flush=True)
        message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
        context2=prepare_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        with DualSearch(context2,device,session.is_current)as search:
            owned=tuple(p.value for lane in search.backend.lanes for p in lane.owned)
            for count in (5,7):
                hit,cursor=search.advance(count)
                if hit is not None:raise RuntimeError('unexpected tiny-target hit')
                if owned!=tuple(p.value for lane in search.backend.lanes for p in lane.owned):
                    raise RuntimeError('dual windows reallocated buffers')
            if cursor.next_tile!=12 or search.backend.dispatches!=4:raise RuntimeError('paired miss cursor differs')
        report['retained_two_windows']=True
        with DualSearch(context2,device,session.is_current,start=search.plan.count-1)as search:
            hit,cursor=search.advance(8192)
            if hit is not None or cursor.next_tile!=search.plan.count or search.backend.dispatches!=1:
                raise RuntimeError('single final tile handling differs')
        report['single_tail_passed']=True
        search=DualSearch(context2,device,session.is_current);original=device.api;replaced=[False]
        def replace_after_launch(name,types,*values):
            result=original(name,types,*values)
            if name=='cuLaunchKernel'and not replaced[0]:replaced[0]=True;session.consume(message)
            return result
        device.api=replace_after_launch
        try:
            try:search.advance(2)
            except StaleWork:pass
            else:raise RuntimeError('replaced in-flight dual pair was accepted')
        finally:device.api=original
        if (not replaced[0]or search.cursor.next_tile!=0 or not search.closed
                or not search.backend.closed or any(lane.pending for lane in search.backend.lanes)):
            raise RuntimeError('stale pair advanced cursor or retained GPU work')
        report['inflight_stale_pair_rejected']=True
        try:build_proof(context,proof_hit,session.is_current)
        except StaleWork:report['stale_proof_rejected']=True
        else:raise RuntimeError('old proof remained current')
        if device.allocations:raise RuntimeError('nonce allocations leaked')
        print('PASS: retained buffers, odd windows, final single tile and in-flight replacement with zero stale cursor credit.',flush=True)
        report['complete']=True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        session.close()
        for resource in (search,device):
            if resource is not None:
                try:resource.close()
                except Exception as exc:report['error']=report['error']or('cleanup: '+str(exc))
        report['complete']=report['complete']and report['error']is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('Dual-stream search preflight complete. No pool connection or shares sent.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
