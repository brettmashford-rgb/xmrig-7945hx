#!/usr/bin/env python3
"""Periodic range scheduling through the validated GPU tile-scan backend.

Synthetic supplied seeds/constant-signal profiles only. Tests bounded windows
of a production-sized domain; does NOT scan a complete nonce or contact a pool.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern
from reference.pool_nonce import nonce_tail
from reference.tile_ranges import PatternDomain,RangePlan,RangeCursor,run_range
from tools.check_noise_mma_gpu import NoiseCase
from tools.check_tile_scan_gpu import MAX_BOUND,TileQuery,TileScanner,ScanResult,query_reference


@dataclass(frozen=True)
class ConstantProfile:
    m:int
    n:int
    k:int
    rank:int
    fill:int
    tail:bytes
    seed_a:bytes
    seed_b:bytes

    def __post_init__(self):
        if (any(type(v)is not int for v in (self.m,self.n,self.k,self.rank,self.fill))
            or not 32<=self.rank<=1024 or self.rank&(self.rank-1)
            or not 0<self.k<=65536 or self.k%self.rank or not -64<=self.fill<=64
            or any(not 0<dim<=0xffffffff//self.rank+1 or dim*self.k>8*1024**3 for dim in (self.m,self.n))
            or type(self.tail)is not bytes or len(self.tail)!=16
            or any(not -64<=(v if v<128 else v-256)<=64 for v in self.tail)
            or any(type(seed)is not bytes or len(seed)!=32 for seed in (self.seed_a,self.seed_b))):
            raise ValueError('invalid constant-signal range profile')

    def case(self,batch):
        if any(not 0<=v<self.m for v in batch.rows)or any(not 0<=v<self.n for v in batch.cols):
            raise ValueError('batch index outside signal matrices')
        a=[self.fill]*(len(batch.rows)*self.k);b=[self.fill]*(len(batch.cols)*self.k)
        for slot,row in enumerate(batch.rows):
            if row==self.m-1:
                a[(slot+1)*self.k-16:(slot+1)*self.k]=[v if v<128 else v-256 for v in self.tail]
        return NoiseCase('range batch',self.k,self.rank,list(batch.rows),list(batch.cols),
                         a,b,self.seed_a,self.seed_b)


class RangeBackend:
    """Correctness backend: CPU references every tested tile; not a benchmark.

    Device signal/noise inputs are held across an overflow retry, then released
    at the next batch. At most32 selected rows/columns are resident per side.
    """
    def __init__(self,profile,device=None,*,bound=MAX_BOUND):
        if type(bound)is not int or not 0<=bound<=MAX_BOUND:raise ValueError('invalid already-scaled bound')
        self.bound=bound
        self.profile=profile;self.device=device;self.batch=None;self.launches=0
        self.mark=len(device.allocations)if device else 0

    def close(self):
        if self.device:
            for pointer in reversed(self.device.allocations[self.mark:]):self.device.release(pointer)
        self.batch=None

    def __call__(self,batch,capacity,generation):
        if batch!=self.batch:
            self.close();case=self.profile.case(batch);self.matrix=case.matrix()
            self.queries=[TileQuery(*mapping)for mapping in batch.maps]
            self.reference=query_reference(self.matrix,self.queries)
            if self.device:
                self.a,self.key=self.device.generate_side(case,case.sides()[0],self.matrix.a)
                self.b,_=self.device.generate_side(case,case.sides()[1],self.matrix.bt)
            self.batch=batch
        self.launches+=1;n=len(batch.maps)
        if not self.device:
            hits={i:digest for i,(_,digest)in enumerate(self.reference)
                  if int.from_bytes(digest,'little')<=self.bound}
            return ScanResult(len(hits),len(hits)>capacity,dict(list(hits.items())[:capacity]))
        return self.device.scan(self.matrix,self.queries,self.reference,self.a,self.b,self.key,
                                [self.bound]*n,capacity,generation,audit=True)


def plans():
    seed_a=small_hash(b'pearlhash/range/v015/A');seed_b=small_hash(b'pearlhash/range/v015/B')
    tail=nonce_tail(bytes(range(8)),bytes(range(8,16)))
    single=PeriodicPattern(bytes(6))
    small=ConstantProfile(3,5,1056,32,64,tail,seed_a,seed_b)
    yield 'small-cancel-resume',small,RangePlan(PatternDomain(3,single),PatternDomain(5,single),batch_queries=4)
    rows=PeriodicPattern.from_list([0,1,8,9,16,17,24,25,32,33])
    cols=PeriodicPattern.from_list([0,1,8,9,32,33,40,41,64,65,72,73,96,97,104,105])
    large=ConstantProfile(5121,262144,32768,128,64,tail,seed_a,seed_b)
    yield 'production-sized',large,RangePlan(PatternDomain(large.m,rows),PatternDomain(large.n,cols))


def exercise(profile,plan,device,start,stop,*,cancel=False):
    backend=RangeBackend(profile,device);cursor=RangeCursor(0x12345678abcdef01,start,stop)
    current=[cursor.generation];seen={};changed=[False]
    def deliver(records):
        for tile,digest,tag in records:
            if tile in seen or tag!=cursor.generation:raise RuntimeError('duplicate/stale range delivery')
            seen[tile]=digest
        if cancel and not changed[0]:
            changed[0]=True;current[0]+=1
    try:
        run_range(plan,cursor,backend,lambda:current[0],deliver)
        if cancel:
            if cursor.status!='cancelled'or not start<cursor.next_tile<stop:
                raise RuntimeError('range did not cancel at the next bounded batch')
            current[0]=cursor.generation
            run_range(plan,cursor,backend,lambda:current[0],deliver)
        if cursor.status!='complete'or cursor.next_tile!=stop or set(seen)!=set(range(start,stop)):
            raise RuntimeError('range completion/candidate coverage differs')
        if cursor.retries==0:raise RuntimeError('queue overflow retry was not exercised')
        return {'tiles_checked':len(seen),'batches':cursor.batches_done,'overflow_retries':cursor.retries,
                'cancel_resume_checked':cancel}
    finally:backend.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/tile-scan-sm120.cubin')
    parser.add_argument('--report',type=Path,help='new local completion report')
    parser.add_argument('--cpu-only',action='store_true')
    args=parser.parse_args()
    if args.report and (args.report.exists()or not args.report.parent.is_dir()):
        raise ValueError('report already exists or its parent directory is missing')
    device=None;checks=[]
    try:
        if not args.cpu_only:
            device=TileScanner();device.start(args.cubin)
        for name,profile,plan in plans():
            if name=='small-cancel-resume':
                print('Checking bounded cancellation/resume and nonce-tail signal rows...',flush=True)
                checks.append(exercise(profile,plan,device,0,plan.count,cancel=True))
                print(f'{"CPU-ONLY"if args.cpu_only else "PASS"}: small range cancelled/resumed; all 15 tiles delivered once; overflow retries complete',flush=True)
            else:
                if plan.count!=8388608:raise RuntimeError('production domain tile count differs')
                for label,start in (('start',0),('middle',plan.count//2),('end',plan.count-2)):
                    print(f'Checking production-sized domain {label} window (2 tiles only)...',flush=True)
                    checks.append(exercise(profile,plan,device,start,start+2))
                    comparison='CPU references prepared'if args.cpu_only else 'CPU/GPU candidates agree'
                    print(f'{"CPU-ONLY"if args.cpu_only else "PASS"}: production-sized {label} window; {comparison}; mapped indices, cursor and retry checked',flush=True)
    finally:
        if device:device.close()
    if args.report:
        with args.report.open('x')as out:
            json.dump({'complete':True,'gpu_checked':not args.cpu_only,'windows':checks,
                       'production_domain_tiles':8388608,'production_tiles_actually_tested':6,
                       'scope':'synthetic bounded range/cursor tests; supplied seeds; no full nonce search, pool submission or performance claim'},out,indent=2)
    print('Synthetic range checks only: 15 small-domain tiles and 6 production-domain tiles, not a full nonce. No pool submission or performance claim.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError)as error:
        print('FAIL:',error);raise SystemExit(1)
