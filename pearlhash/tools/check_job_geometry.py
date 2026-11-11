#!/usr/bin/env python3
"""Reused CPU plan/GPU maps versus v062, with fresh nonces/proofs and guard faults. ISC."""
import argparse
import base64
import ctypes as C
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.compare_search_loops import production_session
from tools.check_prepared_job import synthetic_session
from tools.production_scan import ProductionCandidateScanner
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.job_b_tables import JobBTables,new_job_b_search
from tools.job_geometry import JobGeometry,new_geometry_search
from tools.fast_plan import FastBatch
from tools.shared_b_scan import RowPairQueries,canonical_tile
from tools.virtual_scan import global_reference
from tools.check_tile_scan_gpu import MAX_BOUND
from pool.search import build_proof,StaleWork


def target_cases(search,report):
    d=search.backend.dispatch;p=search.context.profile
    for first in (0,search.plan.count//2,search.plan.count-1):
        batch=FastBatch(search.plan,first,first+1);query=RowPairQueries(batch)[0]
        transcript,digest=global_reference(p,(query,))[0];equal=int.from_bytes(digest,'little')
        for bound,capacity in ((MAX_BOUND,1),(0,1),(equal,1),(max(0,equal-1),1),(MAX_BOUND,0),(0,0)):
            d.bound=bound;d.upload(d.targets[1],bound.to_bytes(32,'little')*4096)
            before=d.device.verified_tiles
            result=d.scan_window(batch,d.prepare_window(batch),(1<<63)+65,capacity=capacity,audit=True)
            expected=int(equal<=bound)
            if (result.total!=expected or result.overflow!=(expected>capacity)
                    or d.device.last_transcripts!=(struct.unpack('<16I',transcript),)):
                raise RuntimeError('geometry target/queue/transcript differs from CPU')
            if not result.overflow and result.records!=({0:digest}if expected else{}):raise RuntimeError('geometry CPU hit differs')
            if result.overflow and d.device.verified_tiles!=before:raise RuntimeError('geometry credited partial queue')
            report['target_cases']+=1
    d.bound=MAX_BOUND;d.upload(d.targets[1],MAX_BOUND.to_bytes(32,'little')*4096)
    batch=FastBatch(search.plan,search.plan.count-67,search.plan.count);before=d.device.verified_tiles
    result=d.scan_window(batch,d.prepare_window(batch),(1<<63)+65,capacity=1)
    if result.total!=67 or not result.overflow or len(result.records)!=1 or d.device.verified_tiles!=before:
        raise RuntimeError('geometry populated overflow differs')
    for index,digest in result.records.items():
        if global_reference(p,(RowPairQueries(batch)[index],))[0][1]!=digest:raise RuntimeError('geometry partial record differs')
    report['partial_queues_checked']+=1


def restore_retained_guard(device,b_owner,geometry,address):
    raw,u,praw,p,rows=b_owner.buffer
    buffers=tuple(geometry.axes)+((raw,u,rows*b_owner.profile.rank),(praw,p,b_owner.profile.k*4))
    if address.value in {a for raw,pointer,size in buffers for a in(raw.value,raw.value+size+16)}:
        data=C.create_string_buffer(b'\xa5'*16,16)
        device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],address,data,16)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,
        gpu_scanner='shared-B-v060',modes_checked=2,production_nonces=0,transcript_windows=0,
        cpu_samples=0,target_cases=0,partial_queues_checked=0,guard_cases=0,official_cpu_verifiers=0,
        retained_windows_and_stale_rejected=False,map_payload_checked=False,geometry_reused=False)
    session=device=b_owner=None;owners=[]
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        owners=[JobGeometry(device,job,session.is_current,maps=maps)for maps in(False,True)]
        for axis,entries in zip(owners[1].axes,(owners[1].plan.rows,owners[1].plan.cols)):
            if owners[1].read(axis[1],0,axis[2])!=b''.join(v.packed for v in entries):raise RuntimeError('resident axis payload differs')
        report['map_payload_checked']=True;map_pointers=tuple(v[0].value for v in owners[1].axes)
        for nonce in range(2):
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            if b_owner is None:b_owner=JobBTables(device,context,session.is_current)
            expected=[]
            with new_job_b_search(context,device,session.is_current,b_owner)as control:
                for first in (1,control.plan.count-4096):
                    batch=FastBatch(control.plan,first,first+4096);d=control.backend.dispatch
                    result=d.scan_window(batch,d.prepare_window(batch),job.generation,capacity=0,audit=True)
                    if result.total:raise RuntimeError('unexpected tiny-target geometry control hit')
                    expected.append((first,device.last_transcripts))
            for geometry in owners:
                with new_geometry_search(context,device,session.is_current,b_owner,geometry)as search:
                    if search.plan is not geometry.plan:raise RuntimeError('geometry plan rebuilt')
                    for first,words in expected:
                        batch=FastBatch(search.plan,first,first+4096);d=search.backend.dispatch
                        result=d.scan_window(batch,d.prepare_window(batch),job.generation,capacity=0,audit=True)
                        if result.total or device.last_transcripts!=words:raise RuntimeError('cached geometry transcript differs from v062')
                        for index in (0,4095):
                            transcript,_=global_reference(context.profile,(RowPairQueries(batch)[index],))[0]
                            if words[index]!=struct.unpack('<16I',transcript):raise RuntimeError('geometry independent CPU transcript differs')
                            report['cpu_samples']+=1
                        report['transcript_windows']+=1
                    if nonce==0:target_cases(search,report)
                if geometry.leased:raise RuntimeError('closed nonce retained geometry lease')
            report['production_nonces']+=1
            print('PASS: production geometry nonce',str(nonce+1)+'/2 compared with v062.',flush=True)
        if any(g.leases!=2 for g in owners)or tuple(v[0].value for v in owners[1].axes)!=map_pointers:
            raise RuntimeError('production geometry was not retained across nonces')
        report['geometry_reused']=True
        for resource in (*owners,b_owner):resource.close()
        owners=[];b_owner=None
        if device.allocations:raise RuntimeError('production geometry cleanup leaked allocations')
        device.close();device=None;session.close()
        session,job,message=synthetic_session(secrets.token_bytes(32));large=message['result'][2]
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        for mode,maps in (('plan',False),('maps',True)):
            message['result'][2]=large;job=session.consume(message)
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            if b_owner is None:b_owner=JobBTables(device,context,session.is_current)
            geometry=JobGeometry(device,job,session.is_current,maps=maps);owners.append(geometry)
            with new_geometry_search(context,device,session.is_current,b_owner,geometry,start=1)as search:
                hit,cursor=search.advance(1)
                if hit is None or hit.tile!=canonical_tile(search.plan,1):raise RuntimeError('geometry canonical proof hit absent')
                proof,_=build_proof(context,hit,session.is_current)
            path=args.output_dir/('geometry-'+mode+'-proof-v3.json')
            path.write_text(json.dumps(dict(cert_version=3,header_base64=base64.b64encode(job.header).decode(),
                plain_proof_base64=base64.b64encode(proof).decode(),share_nbits=None))+'\n')
            subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,
                env=dict(os.environ,RAYON_NUM_THREADS='2'))
            report['official_cpu_verifiers']+=1
            message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
            context=prepare_cached_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            with new_geometry_search(context,device,session.is_current,b_owner,geometry)as search:
                retained=tuple(v.value for v in search.backend.dispatch.owned)
                for amount in (5,7):
                    hit,cursor=search.advance(amount)
                    if hit is not None or tuple(v.value for v in search.backend.dispatch.owned)!=retained:
                        raise RuntimeError('geometry retained odd window differs')
                if cursor.next_tile!=12:raise RuntimeError('geometry cursor differs')
                session.consume(message)
                try:search.advance(1)
                except StaleWork:pass
                else:raise RuntimeError('geometry accepted stale search')
                if not search.closed or geometry.leased:raise RuntimeError('stale geometry cleanup differs')
            job=session.consume(message)
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            for index in range(28):
                search=new_geometry_search(context,device,session.is_current,b_owner,geometry)
                d=search.backend.dispatch;address=C.c_ulonglong(d.guard_addresses[index])
                try:
                    d.upload(address,bytes(16))
                    try:search.advance(1)
                    except RuntimeError as error:
                        if 'guard'not in str(error):raise
                    else:raise RuntimeError('geometry accepted corrupted guard')
                    report['guard_cases']+=1
                finally:
                    restore_retained_guard(device,b_owner,geometry,address);search.close()
            geometry.close();owners.remove(geometry)
            print('PASS:',mode,'geometry -> fresh V3 proof; all guards, target refresh and stale cleanup.',flush=True)
        report['retained_windows_and_stale_rejected']=True
        b_owner.close();b_owner=None
        if device.allocations:raise RuntimeError('geometry preflight leaked GPU allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        if session is not None:session.close()
        for resource in (*owners,b_owner,device):
            if resource is not None:
                try:resource.close()
                except Exception as error:report['error']=report['error']or('cleanup: '+str(error))
        report['complete']=report['complete']and report['error']is None
        (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('GEOMETRY PREFLIGHT:',json.dumps(report),flush=True)
    return 0 if report['complete']else 1

if __name__=='__main__':raise SystemExit(main())
