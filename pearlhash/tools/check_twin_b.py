#!/usr/bin/env python3
"""Fresh two-nonce GPU gates versus v070, independent CPU samples and V3 proofs. ISC."""
import argparse,base64,ctypes as C,json,os,secrets,struct,subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.search import build_proof,Hit,StaleWork
from tools.compare_cta_b import production_session
from tools.check_prepared_job import synthetic_session
from tools.gpu_base import prepare_gpu_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.production_scan import ProductionCandidateScanner
from tools.cta_b_scan import new_cta_search
from tools.check_pair_depth import canonical_window,restore_retained_guard
from tools.pair_depth_scan import canonical,Batch,Queries
from tools.virtual_scan import global_reference
from tools.check_tile_scan_gpu import MAX_BOUND
from tools.twin_b_scan import Twin,JobInputs,MODES


def contexts_for(job,base,frontier,current):
    contexts=tuple(prepare_cached_nonce(job,base,b'TESTWORK',secrets.token_bytes(8),current,frontier)for _ in range(2))
    if contexts[0].profile.seed_b!=contexts[1].profile.seed_b:raise RuntimeError('B is nonce-dependent')
    return contexts


def set_bound(twin,bound):
    for d in twin.dispatches:d.bound=bound;d.upload(d.targets[1],bound.to_bytes(32,'little')*d.capacity)


def reference_at(twin,first):
    query=Queries(Batch(twin.plan,first,first+1),'pair-direct')[0]
    return tuple(global_reference(c.profile,(query,))[0]for c in twin.contexts)


def target_cases(twin,mode,report):
    for first in(0,twin.plan.count//2,twin.plan.count-1):
        refs=reference_at(twin,first);equal=[int.from_bytes(d,'little')for _,d in refs]
        cases=((MAX_BOUND,1),(0,1),(equal[0],1),(max(0,equal[0]-1),1),
               (equal[1],1),(max(0,equal[1]-1),1),(MAX_BOUND,0),(0,0))
        for bound,capacity in cases:
            set_bound(twin,bound);results=twin.scan(mode,first,1,capacity=capacity,audit=True)
            for lane,(r,(transcript,digest))in enumerate(zip(results,refs)):
                expected=int(equal[lane]<=bound)
                if r.total!=expected or r.overflow!=(expected>capacity):raise RuntimeError('nonce target/overflow differs')
                if twin.last_traces[lane]!=(struct.unpack('<16I',transcript),):raise RuntimeError('nonce target CPU transcript differs')
                if not r.overflow and r.records!=({0:digest}if expected else{}):raise RuntimeError('nonce target digest differs')
                report['lane_target_cases']+=1
    set_bound(twin,MAX_BOUND)
    first=twin.plan.count-67
    for lane,r in enumerate(twin.scan(mode,first,67,capacity=1)):
        if r.total!=67 or not r.overflow or len(r.records)!=1:raise RuntimeError('nonce partial queue differs')
        for index,digest in r.records.items():
            if reference_at(twin,first+index)[lane][1]!=digest:raise RuntimeError('partial queue nonce binding differs')
        report['partial_queues']+=1
    for r in twin.scan(mode,0,16384,capacity=0):
        if r.total!=16384 or not r.overflow or r.records:raise RuntimeError('nonce 16K overflow differs')
        report['full_16k_overflows']+=1
    set_bound(twin,twin.contexts[0].job.share_bound)


def invalid_axes(twin,mode,report):
    set_bound(twin,MAX_BOUND);g=twin.inputs.geometry;rows=len(twin.plan.rows);cols=len(twin.plan.cols)
    for side,first,index,limit in((0,0,15, twin.contexts[0].profile.m),
            (0,twin.plan.count-1,rows-1,twin.contexts[0].profile.m),
            (1,0,0,twin.contexts[0].profile.n),(1,twin.plan.count-1,cols-1,twin.contexts[0].profile.n)):
        axis=g.axes[side];pointer=C.c_ulonglong(axis[1].value+index*128);saved=g.read(pointer,0,4)
        try:
            twin.dispatches[0].upload(pointer,struct.pack('<I',limit))
            if any(r.total for r in twin.scan(mode,first,1,capacity=1)):raise RuntimeError('invalid axis accepted')
            report['invalid_axis_scans']+=1
        finally:twin.dispatches[0].upload(pointer,saved)
    set_bound(twin,twin.contexts[0].job.share_bound)


def production_checks(args,report):
    session=device=inputs=None
    try:
        session,job=production_session();base=prepare_gpu_base(job,session.is_current,args.commitment_module)
        front=NonceCommitmentCache.build(job,session.is_current);device=ProductionCandidateScanner();device.start(args.module)
        for pair_index in range(2):
            contexts=contexts_for(job,base,front,session.is_current)
            if inputs is None:
                inputs=JobInputs(device,contexts[0],session.is_current)
                for axis,entries in zip(inputs.geometry.axes,(inputs.geometry.plan.rows,inputs.geometry.plan.cols)):
                    if inputs.geometry.read(axis[1],0,axis[2])!=b''.join(e.packed for e in entries):raise RuntimeError('map payload differs')
                report['map_payload_checked']=True
            with Twin(contexts,device,session.is_current,inputs)as twin:
                if twin.plan.count!=8388608:raise RuntimeError('production domain differs')
                windows=(0,32*len(twin.plan.cols)-33,twin.plan.count//2+1,twin.plan.count-16384)
                expected={}
                for lane,c in enumerate(contexts):
                    with new_cta_search(c,device,session.is_current,inputs.b_pool.view(),inputs.geometry_pool.view(),mode='cta8-v070')as control:
                        for first in windows:expected[lane,first]=canonical_window(control,first,16384,'pair-direct',job.generation)
                for first in windows:
                    results=twin.scan(args.mode,first,16384,audit=True)
                    if any(r.total for r in results):raise RuntimeError('unexpected tiny-target hit')
                    for lane in(0,1):
                        if twin.last_traces[lane]!=expected[lane,first]:raise RuntimeError('two-nonce transcript differs from independent v070')
                        for offset in(0,16383):
                            transcript,_=reference_at(twin,first+offset)[lane]
                            if twin.last_traces[lane][offset]!=struct.unpack('<16I',transcript):raise RuntimeError('independent nonce CPU sample differs')
                            report['cpu_samples']+=1
                        report['transcript_windows']+=1
                if pair_index==0:target_cases(twin,args.mode,report);invalid_axes(twin,args.mode,report)
            if inputs.b_pool.users or inputs.geometry_pool.users:raise RuntimeError('pair retained leases')
            report['production_pairs']+=1;report['production_nonces']+=2
            print('PASS:',args.mode,'fresh production pair',pair_index+1,'/2; both nonces compared with v070.',flush=True)
        report['retained_job_inputs_checked']=True
    finally:
        for resource in(inputs,device,session):
            if resource is not None:resource.close()
        if device is not None and device.allocations:raise RuntimeError('production pair leaked allocations')


def odd_checks(args,report):
    from tools.check_layout_width import odd_column_session
    from pool.search import prepare_base
    session=device=inputs=None
    try:
        session,job=odd_column_session(secrets.token_bytes(32));base=prepare_base(job,session.is_current)
        front=NonceCommitmentCache.build(job,session.is_current);contexts=contexts_for(job,base,front,session.is_current)
        device=ProductionCandidateScanner();device.start(args.module);inputs=JobInputs(device,contexts[0],session.is_current)
        with Twin(contexts,device,session.is_current,inputs)as twin:
            expected=[]
            for c in contexts:
                with new_cta_search(c,device,session.is_current,inputs.b_pool.view(),inputs.geometry_pool.view(),mode='cta8-v070')as control:
                    expected.append(canonical_window(control,0,twin.plan.count,'pair-direct',job.generation))
            for first,count in((0,144),(31,2),(32,1),(64,16),(143,1),(71,7)):
                if any(r.total for r in twin.scan(args.mode,first,count,audit=True)):raise RuntimeError('odd tiny-target hit')
                if twin.last_traces!=tuple(e[first:first+count]for e in expected):raise RuntimeError('odd-column nonce transcript differs')
                report['odd_windows']+=1
            for first in(0,143):
                for lane,(transcript,digest)in enumerate(reference_at(twin,first)):
                    if expected[lane][first]!=struct.unpack('<16I',transcript):raise RuntimeError('odd CPU transcript differs')
                    report['odd_cpu_samples']+=1
    finally:
        for resource in(inputs,device,session):
            if resource is not None:resource.close()
        if device is not None and device.allocations:raise RuntimeError('odd pair leaked allocations')


def proof_guard_checks(args,report):
    session=device=inputs=None
    try:
        session,job,message=synthetic_session(secrets.token_bytes(32))
        base=prepare_gpu_base(job,session.is_current,args.commitment_module);front=NonceCommitmentCache.build(job,session.is_current)
        contexts=contexts_for(job,base,front,session.is_current);device=ProductionCandidateScanner();device.start(args.module)
        inputs=JobInputs(device,contexts[0],session.is_current)
        with Twin(contexts,device,session.is_current,inputs)as twin:
            results=twin.complete_scan(args.mode,5,1)
            for lane,(context,result)in enumerate(zip(contexts,results)):
                if result.total!=1:raise RuntimeError('fresh nonce proof hit missing')
                hit=Hit(job.generation,canonical(twin.plan,'pair-direct',5),result.records[0])
                proof,_=build_proof(context,hit,session.is_current)
                path=args.output_dir/('nonce-'+str(lane)+'-v3.json')
                path.write_text(json.dumps(dict(cert_version=3,header_base64=base64.b64encode(job.header).decode(),plain_proof_base64=base64.b64encode(proof).decode(),share_nbits=None))+'\n')
                subprocess.run([str(args.oracle.resolve()),'verify',str(path.resolve())],check=True,timeout=120,env=dict(os.environ,RAYON_NUM_THREADS='2'))
                report['official_cpu_verifiers']+=1
            # A digest from one lane must not verify under the other nonce's independent CPU reference.
            if results[0].records[0]==results[1].records[0]:raise RuntimeError('fresh nonce proof digests unexpectedly alias')
            report['distinct_proof_bindings_checked']=True
        message['result'][2]=(1).to_bytes(32,'little').hex();job=session.consume(message)
        contexts=contexts_for(job,base,front,session.is_current)
        with Twin(contexts,device,session.is_current,inputs)as twin:
            retained=tuple(device.allocations)
            for first,count in((5,5),(10,7)):
                if any(r.total for r in twin.scan(args.mode,first,count)):raise RuntimeError('retained tiny-target hit')
                if tuple(device.allocations)!=retained:raise RuntimeError('pair buffers rebuilt')
            session.consume(message)
            try:twin.scan(args.mode,17,1)
            except StaleWork:pass
            else:raise RuntimeError('stale pair accepted')
            if not twin.closed or inputs.b_pool.users or inputs.geometry_pool.users:raise RuntimeError('stale pair retained inputs')
        job=session.consume(message);contexts=contexts_for(job,base,front,session.is_current)
        for lane in(0,1):
            for index in range(28):
                with Twin(contexts,device,session.is_current,inputs)as twin:
                    d=twin.dispatches[lane];address=C.c_ulonglong(d.guard_addresses[index])
                    try:
                        d.upload(address,bytes(16))
                        try:twin.scan(args.mode,0,1)
                        except RuntimeError as error:
                            if 'guard'not in str(error):raise
                        else:raise RuntimeError('two-nonce guard corruption accepted')
                        report['guard_cases']+=1
                    finally:restore_retained_guard(device,inputs.b,inputs.geometry,address)
        report['retained_and_stale_checked']=True
    finally:
        for resource in(inputs,device,session):
            if resource is not None:resource.close()
        if device is not None and device.allocations:raise RuntimeError('proof pair leaked allocations')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in('module','commitment-module','oracle','output-dir'):parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--mode',choices=MODES,required=True);args=parser.parse_args()
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    report=dict(complete=False,error=None,mode=args.mode,pool_connection=False,submitted_shares=0,
        production_pairs=0,production_nonces=0,transcript_windows=0,cpu_samples=0,lane_target_cases=0,
        partial_queues=0,full_16k_overflows=0,invalid_axis_scans=0,official_cpu_verifiers=0,guard_cases=0,odd_windows=0,odd_cpu_samples=0)
    try:
        production_checks(args,report);odd_checks(args,report);proof_guard_checks(args,report)
        report['complete']=True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as error:report['error']=type(error).__name__+': '+str(error)
    (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('TWIN PREFLIGHT:',json.dumps(report),flush=True)
    return 0 if report['complete']else 1

if __name__=='__main__':raise SystemExit(main())
