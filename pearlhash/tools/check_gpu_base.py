#!/usr/bin/env python3
"""GPU constant commitments versus independent CPU, then a fresh V3 proof. ISC."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.constant_merkle import constant_opening
from reference.native_hash import small_hash
from pool.search import prepare_nonce,build_proof
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import new_fast_search
from tools.gpu_base import prepare_gpu_base
from tools.gpu_constant_merkle import ConstantMerkleGpu
from tools.production_scan import ProductionCandidateScanner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--commitment-module',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if not os.access(args.oracle,os.X_OK):raise ValueError('existing official verifier required')
    args.output_dir.mkdir(parents=True,mode=0o700,exist_ok=False)
    report={'complete':False,'gpu_checked':False,'pool_connection':False,'submitted_shares':0,
            'scope':'offline GPU constant commitments and fresh proof; no live throughput claim'}
    tree=device=session=None;error=None
    try:
        tree=ConstantMerkleGpu();tree.start(args.commitment_module);count=0
        for total in (1,2,3,31,32,33,65,129,8192):
            for tail in (b'',bytes(range(16))):
                key=small_hash(b'constant-commitment/v039/'+str(total).encode()+tail)
                fill=(0,64,255)[total%3];rows=sorted({0,total//2,total-1})
                expected=constant_opening(key,fill,total,rows,1024,tail=tail)
                actual=tree.opening(key,fill,total,rows,1024,tail=tail)
                if actual.serialize()!=expected.serialize():raise RuntimeError('GPU/CPU full opening differs')
                count+=1
        report['small_gpu_cases']=count
        print('PASS: eighteen GPU constant-tree cases match independent CPU roots/openings, including odd trees and tails.',flush=True)
        print('Building one fresh independent CPU reference for the full 8 GiB logical B commitment; this may take about 30 seconds.',flush=True)
        key=small_hash(secrets.token_bytes(32));total=8388608
        started=time.monotonic();expected=constant_opening(key,64,total,[0],32768)
        cpu_seconds=time.monotonic()-started
        print('CPU reference ready; checking the same full production commitment on GPU.',flush=True)
        started=time.monotonic();actual=tree.opening(key,64,total,[0],32768)
        gpu_seconds=time.monotonic()-started
        if actual.serialize()!=expected.serialize():raise RuntimeError('full production GPU commitment differs from independent CPU')
        report['production_root_match']=True
        report['commitment_comparison']={'cpu_seconds':cpu_seconds,'gpu_seconds':gpu_seconds,
            **tree.last_timing,'scope':'one synthetic production commitment, not mining throughput'}
        print('COMMITMENT COMPARISON:',json.dumps(report['commitment_comparison']),flush=True)
        tree.close();tree=None
        session,job,message=synthetic_session(secrets.token_bytes(32))
        print('Checking fresh GPU B commitment -> nonce seeds -> GPU candidate -> independent new V3 proof...',flush=True)
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        context=prepare_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        with new_fast_search(context,device,session.is_current)as search:
            hit,cursor=search.advance(1)
            if hit is None:raise RuntimeError('near-maximum synthetic bound produced no candidate')
            raw,_=build_proof(context,hit,session.is_current)
        proof=args.output_dir/'gpu-base-proof-v3.json'
        proof.write_text(json.dumps({'cert_version':3,'header_base64':base64.b64encode(job.header).decode(),
            'plain_proof_base64':base64.b64encode(raw).decode(),'share_nbits':None})+'\n')
        subprocess.run([str(args.oracle.resolve()),'verify',str(proof.resolve())],check=True,timeout=120,
                       env=dict(os.environ,RAYON_NUM_THREADS='2'))
        report['official_cpu_verifier']='passed';report['complete']=True;report['gpu_checked']=True
        print('PASS: fresh GPU-base V3 proof accepted by official offline CPU verifier.',flush=True)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        if session is not None:session.close()
        for resource in (tree,device):
            if resource is not None:
                try:resource.close()
                except Exception as exc:error=error or('cleanup: '+str(exc))
        report['error']=error;report['complete']=report['complete']and error is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if error:print('STOP:',error,flush=True);return 1
    print('GPU commitment preflight complete. No pool connection or share sent.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
