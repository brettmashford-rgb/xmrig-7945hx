#!/usr/bin/env python3
"""Independent bounded live mining attempt: actual target, at most one share. ISC.

Assigned extranonce is tested as worker_nonce; pool acceptance remains unproven.
No reconnect, captured-share replay, service changes or clock changes.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.receiver import PoolReceiver
from pool.search import prepare_base,prepare_nonce,NonceSearch,require_current
from pool.session import MiningProfile,PoolSession
from pool.submission import SubmissionGate,prepare_share
from pool.worker import LatestJobWorker
from pool.telemetry import WorkTelemetry
from reference.patterns import PeriodicPattern
from tools.check_live_job import saved_wallet
from tools.production_scan import ProductionCandidateScanner
from tools.wide_scan import wide_plan_for
from tools.fast_plan import FastCandidateBackend,FastPlan
from tools.gpu_base import prepare_gpu_base


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True);parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--login-file',type=Path,required=True)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--commitment-module',type=Path,help='explicit GPU constant B commitment module')
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=300)
    parser.add_argument('--observe-target',action='store_true',help='receive one target, no GPU work or submission')
    args=parser.parse_args()
    if not 1<=args.seconds<=300:raise ValueError('bounded receive duration required')
    p=MiningProfile(5121,262144,32768,128,PeriodicPattern(bytes.fromhex('000103040000')),
                    PeriodicPattern(bytes.fromhex('000103010103')))
    session=PoolSession(p,cert_version=3);gate=SubmissionGate(session,max_pending=1)
    stop=threading.Event();heartbeat_done=threading.Event();lock=threading.Lock()
    backend_reports=[]
    state={'tiles':0,'nonces_started':0,'full_nonces':0,'proofs_checked':0,'stage':'waiting for job'}
    telemetry=WorkTelemetry()
    started=time.monotonic();base_cache=[None];last_report=[0.0];last_progress=[0.0]
    def progress(label):
        with lock:state['stage']=label
        print(label,flush=True)
    def heartbeat():
        while not heartbeat_done.wait(15):
            with lock:snapshot=dict(state)
            print(f"Still running: {snapshot['stage']}; completed search tiles {snapshot['tiles']}",flush=True)
    def report_rate():
        now=time.monotonic()
        if now-last_report[0]<15:return
        with lock:tiles=state['tiles']
        # Completed tile dot-product terms, including all preparation elapsed.
        # This deliberately does not count a multiply-add as two operations.
        rate=tiles*p.rows.size*p.cols.size*p.k/max(now-started,1e-9)
        gate.report_info(rate,'PearlHash independent GPU')
        last_report[0]=now
    def process(job,current):
        progress('Live job: preparing the production B commitment on '+('GPU.'if args.commitment_module else 'CPU.'))
        base_started=time.monotonic()
        base=base_cache[0]
        reused=base is not None and (base.job_key,base.n,base.k)==(job.job_key,p.n,p.k)
        telemetry.prepared(job,base_reused=reused)
        try:
            if not reused:
                base=(prepare_gpu_base(job,current,args.commitment_module)if args.commitment_module else prepare_base(job,current))
                base_cache[0]=base
        finally:telemetry.seconds(job,'base',time.monotonic()-base_started)
        require_current(job,current)
        device=ProductionCandidateScanner()
        try:
            device.start(args.module)
            while current(job):
                progress('Preparing a fresh nonce; assigned extranonce is the worker-nonce hypothesis.')
                nonce_started=time.monotonic()
                try:context=prepare_nonce(job,base,job.assigned_extranonce,secrets.token_bytes(8),current)
                finally:telemetry.seconds(job,'nonce',time.monotonic()-nonce_started)
                telemetry.add(job,nonces=1)
                with lock:state['nonces_started']+=1
                cache_started=time.monotonic()
                def generation():
                    require_current(job,current)
                    return job.generation
                def backend_factory(profile,device,*,bound):
                    return FastCandidateBackend(profile,device,plan=plan,bound=bound,
                        current_generation=generation,on_close=backend_reports.append)
                try:
                    plan=FastPlan.from_job(job)
                    search=NonceSearch(context,device,current,backend_factory=backend_factory,plan_factory=lambda job:plan)
                finally:telemetry.seconds(job,'cache',time.monotonic()-cache_started)
                with search:
                    progress('Searching the live production domain; actual pool target retained.')
                    report_rate()
                    while search.cursor.next_tile<search.plan.count:
                        first=search.cursor.next_tile
                        scan_started=time.monotonic()
                        try:hit,cursor=search.advance(4096)
                        finally:telemetry.seconds(job,'search',time.monotonic()-scan_started)
                        telemetry.add(job,tiles=cursor.next_tile-first)
                        with lock:state['tiles']+=cursor.next_tile-first
                        now=time.monotonic()
                        if now-last_progress[0]>=15:
                            progress(f'Search cursor {cursor.next_tile}/{search.plan.count}; nonce cache retained.')
                            last_progress[0]=now
                        report_rate()
                        if hit is not None:
                            progress('Actual-target candidate found; independently checking math and constructing its proof.')
                            proof_started=time.monotonic()
                            try:share=prepare_share(context,hit,current)
                            finally:telemetry.seconds(job,'proof',time.monotonic()-proof_started)
                            with lock:state['proofs_checked']+=1
                            require_current(job,current)
                            request_id=gate.send(share)
                            progress(f'Fresh custom share sent (request {request_id}); waiting for the correlated pool verdict.')
                            # Keep the receiver alive for the verdict, even if a
                            # later notify replaces the already-submitted job.
                            if not stop.wait(30):
                                progress('Share verdict timeout; no retry.');stop.set()
                            return {'submitted':True}
                    telemetry.add(job,full_nonces=1)
                    with lock:state['full_nonces']+=1
                require_current(job,current)
            require_current(job,current)
        finally:device.close()
    def verdict(result):
        print('POOL SHARE VERDICT:',result.outcome,'status:',result.status,flush=True)
        stop.set()
    def received_job(job):
        telemetry.received(job)
        expected=(1<<256)/(job.share_bound+1)
        print(f'Live target: {job.share_bound.bit_length()} scaled bits; mean {expected:.6g} tiles per candidate under uniform-digest model.',flush=True)
        if args.observe_target:stop.set()
        else:worker.publish(job)
    receiver=PoolReceiver(session,args.host,args.port,saved_wallet(args.login_file),'5060-independent-v039',
                          agent='pearlhash-independent/0.0.39')
    worker=LatestJobWorker(session,process,lambda job,result:None,stop=stop)
    fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    beat=threading.Thread(target=heartbeat,name='pearlhash-progress',daemon=True)
    error=None;received=None
    try:
        worker.start();beat.start()
        print('Target-only observation; no GPU work or share submission.'if args.observe_target else
              'One bounded live mining connection; at most one new custom share; no automatic retry.',flush=True)
        received=receiver.run(received_job,stop=stop,seconds=args.seconds,max_messages=256,
                              gate=gate,on_response=verdict)
    except (OSError,ValueError,RuntimeError,UnicodeError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        stop.set();session.close()
        progress('Connection closed; joining search worker. An in-flight native CPU call must finish.')
        worker.close();heartbeat_done.set()
        if beat.is_alive():beat.join()
        if worker.error is not None:error=type(worker.error).__name__+': '+str(worker.error)
        if error is None and not telemetry.snapshot()['jobs']:error='No supported live job received'
        with lock:work=dict(state)
        stats=gate.stats()
        report={'complete':error is None,'receiver':asdict(received)if received else None,
                'worker':worker.stats(),'work':work,'connection':stats,'error':error,
                'telemetry':telemetry.snapshot(),'scan_backend':'validated-axis-production-virtual-v038',
                'backend_lifecycle':backend_reports,
                'commitment_backend':'gpu-constant-v039'if args.commitment_module else 'cpu-streaming',
                'submitted_shares':stats['sent'],'pool_accepted_shares':stats['accepted'],
                'extranonce_worker_role_verified':stats['accepted']>0,
                'reported_rate_unit':'completed scalar dot-product terms per second, whole attempt elapsed',
                'scope':'live target-only observation; no GPU or submission'if args.observe_target else
                        'bounded independent live mining attempt; no overall throughput or power claim'}
        with os.fdopen(fd,'w')as out:json.dump(report,out,indent=2);out.write('\n')
    summary=telemetry.snapshot()
    print('Search summary:',work,flush=True)
    print('Target model: expected candidates',format(summary['expected_candidate_count'],'.6g'),
          '; chance of at least one',format(100*summary['model_probability_at_least_one_candidate'],'.6g')+'%',flush=True)
    print('Stage totals (seconds):',{stage:round(sum(row['seconds'][stage]for row in summary['jobs']),3)
          for stage in ('base','nonce','cache','search','proof')},flush=True)
    print('Worker lifecycle:',worker.stats(),flush=True)
    print('Reusable dispatch totals:',{key:sum(row[key]for row in backend_reports)
          for key in ('prepared_batches','dispatches','dispatch_buffer_allocations')},flush=True)
    print('Connection summary:',stats,flush=True)
    if error:print('STOP:',error,flush=True);return 1
    if args.observe_target:print('Live target observation complete; no GPU work or shares sent.',flush=True)
    elif stats['accepted']:print('CUSTOM SHARE ACCEPTED by the live pool.',flush=True)
    elif stats['sent']:print('Custom share sent; accepted shares:',stats['accepted'],flush=True)
    else:print('Bounded run ended without a submitted share; pool acceptance remains unproven.',flush=True)
    print('Completion saved. Existing miners, services and clocks unchanged.',flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,TypeError,KeyError)as exc:
        print('STOP:',exc,flush=True);raise SystemExit(1)
