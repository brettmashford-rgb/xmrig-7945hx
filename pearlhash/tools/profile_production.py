#!/usr/bin/env python3
"""One live job, actual production row-major windows; diagnostic only. ISC.

No submission gate, report_info messages, proof construction or reconnect. CUDA
intervals overlap host waits. cProfile disturbs timings; plain windows provide
an adjacent control, not identical inputs. Private reports contain aggregates.
"""
import argparse
import cProfile
from dataclasses import asdict
import json
import os
from pathlib import Path
import pstats
import secrets
import sys
import threading
import time

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.receiver import PoolReceiver
from pool.search import NonceSearch,prepare_base,prepare_nonce,require_current
from pool.session import MiningProfile,PoolSession
from pool.worker import LatestJobWorker
from reference.patterns import PeriodicPattern
from tools.check_live_job import saved_wallet
from tools.prepared_backend import PreparedCandidateBackend
from tools.profile_dispatch import ProfileScanner
from tools.wide_scan import WideRangePlan,wide_plan_for


def cpu_rows(profiler,limit=12):
    if not profiler.getstats():return []
    rows=[]
    for (filename,line,function),(primitive,calls,own,cumulative,callers) in pstats.Stats(profiler).stats.items():
        rows.append({'function':Path(filename).name+':'+str(line)+':'+function,
                     'calls':calls,'self_seconds':own,'cumulative_seconds':cumulative})
    return sorted(rows,key=lambda row:row['cumulative_seconds'],reverse=True)[:limit]


class TimedPlan(WideRangePlan):
    def __init__(self,a,b):
        super().__init__(a,b);self.planning_seconds=0.
    def batches(self,start,stop):
        iterator=iter(super().batches(start,stop))
        while True:
            started=time.perf_counter()
            try:batch=next(iterator)
            except StopIteration:
                self.planning_seconds+=time.perf_counter()-started;return
            self.planning_seconds+=time.perf_counter()-started
            yield batch


class MeasuredBackend(PreparedCandidateBackend):
    def __init__(self,*args,**kwargs):
        self.enabled=False;self.measurements=[]
        super().__init__(*args,**kwargs)
    def __call__(self,*args):
        operation=lambda:super(MeasuredBackend,self).__call__(*args)
        if not self.enabled:return operation()
        result,record=self.device.measure(operation)
        self.measurements.append(record)
        return result


def summarize(records):
    return {'dispatches':len(records),'wall_seconds':sum(r['wall_seconds']for r in records),
            'gpu_event_seconds':sum(r['gpu_event_seconds']for r in records),
            'host_seconds':{key:sum(r['host_seconds'].get(key,0.)for r in records)
                for key in sorted({key for r in records for key in r['host_seconds']})}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login-file',type=Path,required=True)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    p=MiningProfile(5121,262144,32768,128,PeriodicPattern(bytes.fromhex('000103040000')),
                    PeriodicPattern(bytes.fromhex('000103010103')))
    session=PoolSession(p,cert_version=3);stop=threading.Event();done=threading.Event()
    lock=threading.Lock();stage=['waiting for supported live job'];jobs=[]
    fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    def progress(message):
        with lock:stage[0]=message
        print(message,flush=True)
    def heartbeat():
        while not done.wait(15):
            with lock:message=stage[0]
            print('Still running: '+message,flush=True)
    def process(job,current):
        record={'complete':False,'windows':[],'scaled_target_bits':job.share_bound.bit_length()}
        device=None;search=None;profiler=cProfile.Profile()
        try:
            progress('Preparing this live job and fresh nonce on CPU; no share submission.')
            started=time.perf_counter();base=prepare_base(job,current)
            record['base_seconds']=time.perf_counter()-started
            started=time.perf_counter()
            context=prepare_nonce(job,base,job.assigned_extranonce,secrets.token_bytes(8),current)
            record['nonce_seconds']=time.perf_counter()-started
            device=ProfileScanner();device.start(args.module);device.create_events()
            def generation():require_current(job,current);return job.generation
            def factory(profile,device,*,bound):
                return MeasuredBackend(profile,device,bound=bound,current_generation=generation)
            def plan_factory(job):
                plan=wide_plan_for(job);return TimedPlan(plan.a,plan.b)
            search=NonceSearch(context,device,current,backend_factory=factory,plan_factory=plan_factory)
            progress('Profiling 32 consecutive production windows; alternating plain and instrumented calls.')
            for window in range(32):
                measured=bool(window%2);search.backend.enabled=measured
                before=search.cursor.next_tile;planning=search.plan.planning_seconds
                prepare=search.backend.prepare_seconds;scan=search.backend.scan_seconds
                started=time.perf_counter()
                if measured:profiler.enable()
                try:hit,cursor=search.advance(4096)
                finally:profiler.disable()
                record['windows'].append({'instrumented':measured,'tiles':cursor.next_tile-before,
                    'wall_seconds':time.perf_counter()-started,
                    'planning_seconds':search.plan.planning_seconds-planning,
                    'prepare_seconds':search.backend.prepare_seconds-prepare,
                    'scan_seconds':search.backend.scan_seconds-scan})
                if hit is not None:
                    record['candidate_found']=True
                    progress('Candidate observed; diagnostic stops without constructing or submitting a proof.')
                    break
            record['complete']=True
            return True
        finally:
            profiler.disable()
            failed=sys.exc_info()[0]is not None;cleanup_error=None
            if search is not None:
                record['dispatch_profile']=summarize(search.backend.measurements)
            for resource in (search,device):
                if resource is not None:
                    try:resource.close()
                    except Exception as exc:cleanup_error=cleanup_error or exc
            if search is not None:record['backend']=search.backend.stats()
            record['cpu_functions']=cpu_rows(profiler)
            if cleanup_error is not None:record['complete']=False;record['cleanup_error']=str(cleanup_error)
            jobs.append(record)
            if cleanup_error is not None and not failed:raise cleanup_error
    def completed(job,result):stop.set()
    worker=LatestJobWorker(session,process,completed,stop=stop)
    thread=threading.Thread(target=heartbeat,daemon=True);error=None;received=None
    try:
        receiver=PoolReceiver(session,'pool.pearlhash.xyz',9000,saved_wallet(args.login_file),
                              '5060-profile-v037',agent='pearlhash-independent/0.0.37-diagnostic')
        worker.start();thread.start()
        print('One live diagnostic connection, up to 90 seconds. Actual target; no shares or status reports.',flush=True)
        received=receiver.run(worker.publish,stop=stop,seconds=90,max_messages=128)
    except (OSError,ValueError,RuntimeError,UnicodeError)as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        stop.set();session.close();worker.close();done.set()
        if thread.is_alive():thread.join()
        if worker.error is not None:error=type(worker.error).__name__+': '+str(worker.error)
        if not any(row['complete']for row in jobs)and error is None:error='No complete diagnostic before deadline or job replacement'
        with os.fdopen(fd,'w')as output:
            json.dump({'complete':error is None,'error':error,'jobs':jobs,'worker':worker.stats(),
                'receiver':asdict(received)if received else None,'submitted_shares':0,
                'scope':'live production-window profiling; no proof, mining throughput or pool acceptance claim'},output,indent=2)
            output.write('\n')
    for index,job in enumerate(jobs):
        print('JOB PROFILE',index+1,'base_seconds:',round(job.get('base_seconds',0.),6),flush=True)
        for measured,label in ((False,'PLAIN'),(True,'INSTRUMENTED')):
            windows=[w for w in job['windows']if w['instrumented']==measured]
            print(label+' WINDOWS:',json.dumps({key:sum(w[key]for w in windows)for key in
                ('tiles','wall_seconds','planning_seconds','prepare_seconds','scan_seconds')}),flush=True)
        print('DISPATCH PROFILE:',json.dumps(job.get('dispatch_profile',{}),sort_keys=True),flush=True)
        print('CPU FUNCTIONS:',json.dumps(job['cpu_functions']),flush=True)
    if error:print('STOP:',error,flush=True);return 1
    print('Production profiling complete. No proof or share submitted.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
