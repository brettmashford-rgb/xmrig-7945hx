#!/usr/bin/env python3
"""v078 64-tile blocks and larger dispatches versus actual v070 control, fresh proofs. ISC."""
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
from tools.job_b_tables import JobBTables
from tools.job_geometry import JobGeometry
from functools import partial
from tools.cta_b_scan import new_cta_search,cta_traversal_ordinal
from tools.throughput_scan import new_search,Batch,Queries,canonical,layout,inverse,MODES,LIMITS
from tools.hoisted_a_scan import new_hoisted_a_search
from tools.cta_b_scan import CtaBQueries,cta_canonical_tile
from tools.four_tile_scan import four_traversal_ordinal
from tools.fast_plan import FastBatch
from tools.virtual_scan import global_reference
from tools.check_tile_scan_gpu import MAX_BOUND
from pool.search import build_proof,StaleWork


def target_cases(search,report):
    d=search.backend.dispatch;p=search.context.profile
    for first in (0,search.plan.count//2,search.plan.count-1):
        batch=Batch(search.plan,first,first+1);query=Queries(batch,search.mode)[0]
        transcript,digest=global_reference(p,(query,))[0];equal=int.from_bytes(digest,'little')
        for bound,capacity in ((MAX_BOUND,1),(0,1),(equal,1),(max(0,equal-1),1),(MAX_BOUND,0),(0,0)):
            d.bound=bound;d.upload(d.targets[1],bound.to_bytes(32,'little')*d.capacity)
            before=d.device.verified_tiles
            result=d.scan_window(batch,d.prepare_window(batch),(1<<63)+65,capacity=capacity,audit=True)
            expected=int(equal<=bound)
            if (result.total!=expected or result.overflow!=(expected>capacity)
                    or d.device.last_transcripts!=(struct.unpack('<16I',transcript),)):
                raise RuntimeError('geometry target/queue/transcript differs from CPU')
            if not result.overflow and result.records!=({0:digest}if expected else{}):raise RuntimeError('geometry CPU hit differs')
            if result.overflow and d.device.verified_tiles!=before:raise RuntimeError('geometry credited partial queue')
            report['target_cases']+=1
    d.bound=MAX_BOUND;d.upload(d.targets[1],MAX_BOUND.to_bytes(32,'little')*d.capacity)
    batch=Batch(search.plan,search.plan.count-67,search.plan.count);before=d.device.verified_tiles
    result=d.scan_window(batch,d.prepare_window(batch),(1<<63)+65,capacity=1)
    if result.total!=67 or not result.overflow or len(result.records)!=1 or d.device.verified_tiles!=before:
        raise RuntimeError('geometry populated overflow differs')
    for index,digest in result.records.items():
        if global_reference(p,(Queries(batch,search.mode)[index],))[0][1]!=digest:raise RuntimeError('geometry partial record differs')
    report['partial_queues_checked']+=1
    if search.mode in MODES:
        limit=d.limit
        batch=Batch(search.plan,0,limit)
        result=d.scan_window(batch,d.prepare_window(batch),(1<<63)+65,capacity=0)
        if result.total!=limit or not result.overflow or result.records:raise RuntimeError('full dispatch overflow differs')
        report['large_queue_count']=limit
        report['large_queue_checked']=True


def cta_guard_cases(search,report):
    d=search.backend.dispatch;p=search.context.profile
    d.bound=MAX_BOUND;d.upload(d.targets[1],MAX_BOUND.to_bytes(32,'little')*d.capacity)
    row_count=len(search.plan.rows);members=d.group()
    # Last quartet, inactive quartet, last physical row, and column map errors.
    for first,count,row in ((0,1,members-1),(5,1,0),(search.plan.count-1,1,row_count-1)):
        axis=d.axes[0];pointer=C.c_ulonglong(axis[1].value+row*128)
        saved=d.tables.read(pointer,0,4)
        try:
            d.upload(pointer,struct.pack('<I',p.m))
            batch=Batch(search.plan,first,first+count)
            result=d.scan_window(batch,d.prepare_window(batch),search.context.job.generation,capacity=1)
            if result.total or result.records:raise RuntimeError('invalid CTA row map accepted')
            report['cta_guard_cases']+=1
        finally:d.upload(pointer,saved)
    for first in (0,search.plan.count-1):
        tile=canonical(search.plan,search.mode,first);col=tile%len(search.plan.cols)
        pointer=C.c_ulonglong(d.axes[1][1].value+col*128)
        saved=d.tables.read(pointer,0,4)
        try:
            d.upload(pointer,struct.pack('<I',p.n))
            batch=Batch(search.plan,first,first+1)
            result=d.scan_window(batch,d.prepare_window(batch),search.context.job.generation,capacity=1)
            if result.total or result.records:raise RuntimeError('invalid CTA column map accepted')
            report['cta_guard_cases']+=1
        finally:d.upload(pointer,saved)
    d.bound=search.context.job.share_bound
    d.upload(d.targets[1],d.bound.to_bytes(32,'little')*d.capacity)


def restore_retained_guard(device,b_owner,geometry,address):
    raw,u,praw,p,rows=b_owner.buffer
    buffers=tuple(geometry.axes)+((raw,u,rows*b_owner.profile.rank),(praw,p,b_owner.profile.k*4))
    if address.value in {a for raw,pointer,size in buffers for a in(raw.value,raw.value+size+16)}:
        data=C.create_string_buffer(b'\xa5'*16,16)
        device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],address,data,16)


def canonical_window(control,first,count,mode,generation):
    requests=sorted((cta_traversal_ordinal(control.plan,canonical(control.plan,mode,ordinal)),local)
        for local,ordinal in enumerate(range(first,first+count)))
    words=[None]*count;index=0;dispatch=control.backend.dispatch
    while index<count:
        end=index+1
        while end<count and end-index<4096 and requests[end][0]==requests[end-1][0]+1:end+=1
        start=requests[index][0];old=FastBatch(control.plan,start,requests[end-1][0]+1)
        result=dispatch.scan_window(old,dispatch.prepare_window(old),generation,capacity=0,audit=True)
        if result.total:raise RuntimeError('unexpected tiny-target control hit')
        for ordinal,local in requests[index:end]:words[local]=dispatch.device.last_transcripts[ordinal-start]
        index=end
    if any(word is None for word in words):raise RuntimeError('missing canonical control words')
    return tuple(words)


def audit_window(search,first,count):
    words=[];d=search.backend.dispatch;stop=first+count
    while first<stop:
        end=min(stop,first+d.limit)
        if search.mode.startswith('panel'):
            _,column,width,local=layout(search.plan,search.mode,first);end=min(end,first+len(search.plan.rows)*width-local)
        batch=Batch(search.plan,first,end)
        result=d.scan_window(batch,d.prepare_window(batch),search.context.job.generation,capacity=0,audit=True)
        if result.total:raise RuntimeError('unexpected experimental tiny-target hit')
        words.extend(d.device.last_transcripts);first=end
    return tuple(words)


def check_bijection(plan,mode):
    seen=bytearray(plan.count)
    for ordinal in range(plan.count):
        tile=canonical(plan,mode,ordinal)
        if seen[tile]or inverse(plan,mode,tile)!=ordinal:raise RuntimeError('CTA row-group mapping is not a bijection')
        seen[tile]=1
    if sum(seen)!=plan.count:raise RuntimeError('CTA row-group traversal omitted tiles')
    print('PASS: CTA row-group bijection across',plan.count,'canonical tiles.',flush=True)
    return plan.count


def argument_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--mode',choices=MODES,required=True)
    return parser


def main():
    args=argument_parser().parse_args();new_packed_geometry_search=partial(new_search,mode=args.mode);args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    report=dict(complete=False,error=None,pool_connection=False,submitted_shares=0,
        gpu_scanner=args.mode,modes_checked=1,production_nonces=0,transcript_windows=0,
        cpu_samples=0,target_cases=0,partial_queues_checked=0,guard_cases=0,cta_guard_cases=0,official_cpu_verifiers=0,
        retained_windows_and_stale_rejected=False,map_payload_checked=False,geometry_reused=False,canonical_windows_checked=False,large_queue_checked=False)
    session=device=b_owner=None;owners=[]
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        owners=[JobGeometry(device,job,session.is_current,maps=True)]
        for axis,entries in zip(owners[0].axes,(owners[0].plan.rows,owners[0].plan.cols)):
            if owners[0].read(axis[1],0,axis[2])!=b''.join(v.packed for v in entries):raise RuntimeError('resident axis payload differs')
        report['mapping_tiles']=check_bijection(owners[0].plan,args.mode)
        report['map_payload_checked']=True;map_pointers=tuple(v[0].value for v in owners[0].axes)
        for nonce in range(2):
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            if b_owner is None:b_owner=JobBTables(device,context,session.is_current)
            expected=[]
            with new_cta_search(context,device,session.is_current,b_owner,owners[0],mode='cta8-v070')as control:
                count=LIMITS[args.mode]
                for first in (0,64*len(control.plan.cols)-65,control.plan.count//2+1,control.plan.count-count):
                    expected.append((first,canonical_window(control,first,count,args.mode,job.generation)))
            for geometry in owners:
                with new_packed_geometry_search(context,device,session.is_current,b_owner,geometry)as search:
                    if search.plan is not geometry.plan:raise RuntimeError('geometry plan rebuilt')
                    for first,words in expected:
                        count=len(words);batch=Batch(search.plan,first,first+count)
                        actual=audit_window(search,first,count)
                        if actual!=words:raise RuntimeError('experimental transcript differs from v070')
                        for index in (0,count-1):
                            transcript,_=global_reference(context.profile,(Queries(batch,search.mode)[index],))[0]
                            if words[index]!=struct.unpack('<16I',transcript):raise RuntimeError('independent CPU transcript differs')
                            report['cpu_samples']+=1
                        report['transcript_windows']+=1
                    if nonce==0:
                        target_cases(search,report)
                        cta_guard_cases(search,report)
                if geometry.leased:raise RuntimeError('closed nonce retained geometry lease')
            report['production_nonces']+=1
            print('PASS: production geometry nonce',str(nonce+1)+'/2 compared with v070.',flush=True)
        if any(g.leases!=4 for g in owners)or tuple(v[0].value for v in owners[0].axes)!=map_pointers:
            raise RuntimeError('production geometry was not retained across nonces')
        report['geometry_reused']=True;report['canonical_windows_checked']=True
        for resource in (*owners,b_owner):resource.close()
        owners=[];b_owner=None
        if device.allocations:raise RuntimeError('production geometry cleanup leaked allocations')
        device.close();device=None;session.close()
        session,job,message=synthetic_session(secrets.token_bytes(32))
        base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        frontier=NonceCommitmentCache.build(job,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module)
        geometry=JobGeometry(device,job,session.is_current,maps=True);owners.append(geometry)
        for index in range(2):
            context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
            if b_owner is None:b_owner=JobBTables(device,context,session.is_current)
            with new_packed_geometry_search(context,device,session.is_current,b_owner,geometry,start=5)as search:
                hit,cursor=search.advance(1)
                if hit is None or hit.tile!=canonical(search.plan,search.mode,5):raise RuntimeError('combined canonical proof hit absent')
                proof,_=build_proof(context,hit,session.is_current)
            path=args.output_dir/('packed-geometry-proof-'+str(index+1)+'-v3.json')
            path.write_text(json.dumps(dict(cert_version=3,header_base64=base64.b64encode(job.header).decode(),
                plain_proof_base64=base64.b64encode(proof).decode(),share_nbits=None))+'\n')
            subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,
                env=dict(os.environ,RAYON_NUM_THREADS='2'))
            report['official_cpu_verifiers']+=1
            print('PASS: combined fresh nonce',index+1,'-> canonical candidate -> new V3 proof -> official CPU verifier.',flush=True)
        if geometry.leases!=2:raise RuntimeError('combined proof geometry was not reused')
        report['proof_geometry_reused']=True
        message['result'][2]=(1).to_bytes(32,'little').hex();small=session.consume(message)
        context=prepare_cached_nonce(small,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
        with new_packed_geometry_search(context,device,session.is_current,b_owner,geometry)as search:
            retained=tuple(v.value for v in search.backend.dispatch.owned)
            for amount in (5,7):
                hit,cursor=search.advance(amount)
                if hit is not None or tuple(v.value for v in search.backend.dispatch.owned)!=retained:
                    raise RuntimeError('combined retained odd window differs')
            if cursor.next_tile!=12:raise RuntimeError('combined cursor differs')
            session.consume(message)
            try:search.advance(1)
            except StaleWork:pass
            else:raise RuntimeError('combined accepted stale search')
            if not search.closed or geometry.leased:raise RuntimeError('stale combined cleanup differs')
        job=session.consume(message)
        context=prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),session.is_current,frontier)
        for index in range(30 if args.mode.startswith('panel')else 28):
            search=new_packed_geometry_search(context,device,session.is_current,b_owner,geometry)
            d=search.backend.dispatch;address=C.c_ulonglong(d.guard_addresses[index])
            try:
                d.upload(address,bytes(16))
                try:search.advance(1)
                except RuntimeError as error:
                    if 'guard'not in str(error):raise
                else:raise RuntimeError('combined accepted corrupted guard')
                report['guard_cases']+=1
            finally:
                restore_retained_guard(device,b_owner,geometry,address);search.close()
        geometry.close();owners.remove(geometry)
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
    print('EXPERIMENT PREFLIGHT:',json.dumps(report),flush=True)
    return 0 if report['complete']else 1

if __name__=='__main__':raise SystemExit(main())
