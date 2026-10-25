"""Aggregate bounded-run work and target diagnostics; no credential/nonce output. ISC."""
import math
import threading
import time


class WorkTelemetry:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.started=clock();self.lock=threading.RLock()
        self.jobs={};self.previous=None

    def received(self,job):
        with self.lock:
            if job.generation in self.jobs:return
            if len(self.jobs)>=256:raise ValueError('telemetry job budget exceeded')
            old=self.previous
            # Inclusive little-endian digest comparison: B+1 passing values.
            probability=(job.share_bound+1)/(1<<256)
            self.jobs[job.generation]={'generation':job.generation,
                'received_seconds':self.clock()-self.started,
                'scaled_target_bits':job.share_bound.bit_length(),
                'mean_tiles_per_candidate':1/probability,
                'target_probability_per_tile':probability,
                'changes':{name:old is not None and getattr(old,attribute)!=getattr(job,attribute)
                    for name,attribute in (('header','header'),('target','target_bytes'),
                        ('extranonce','assigned_extranonce'),('metadata','opaque_metadata'),('token','opaque_token'))},
                'tiles':0,'full_nonces':0,'nonces_started':0,'base_reused':False,
                'seconds':{name:0.0 for name in ('base','nonce','cache','search','proof')}}
            self.previous=job

    def prepared(self,job,*,base_reused):
        with self.lock:self.jobs[job.generation]['base_reused']=bool(base_reused)

    def add(self,job,*,tiles=0,nonces=0,full_nonces=0):
        if any(type(v)is not int or v<0 for v in (tiles,nonces,full_nonces)):
            raise ValueError('nonnegative work counters required')
        with self.lock:
            row=self.jobs[job.generation]
            row['tiles']+=tiles;row['nonces_started']+=nonces;row['full_nonces']+=full_nonces

    def seconds(self,job,stage,elapsed):
        if stage not in ('base','nonce','cache','search','proof')or not math.isfinite(elapsed)or elapsed<0:
            raise ValueError('finite stage duration required')
        with self.lock:self.jobs[job.generation]['seconds'][stage]+=elapsed

    def snapshot(self):
        with self.lock:
            rows=[dict(row,changes=dict(row['changes']),seconds=dict(row['seconds']))for row in self.jobs.values()]
            elapsed=max(0.0,self.clock()-self.started)
        tiles=sum(row['tiles']for row in rows)
        expected=sum(row['tiles']*row['target_probability_per_tile']for row in rows)
        log_no_hit=sum(row['tiles']*math.log1p(-row['target_probability_per_tile'])
            for row in rows if row['tiles'] and row['target_probability_per_tile']<1)
        certainty=any(row['tiles'] and row['target_probability_per_tile']==1 for row in rows)
        chance=1.0 if certainty else max(0.0,-math.expm1(log_no_hit))
        return {'elapsed_seconds':elapsed,'completed_tiles':tiles,
                'whole_attempt_tiles_per_second':tiles/elapsed if elapsed else 0.0,
                'expected_candidate_count':expected,'model_probability_at_least_one_candidate':chance,
                'probability_scope':'model assumes independent uniformly distributed 256-bit digests; not a pool verdict',
                'jobs':rows}
