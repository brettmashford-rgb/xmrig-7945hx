#!/usr/bin/env python3
"""Fresh synthetic nonce -> commitments/seeds -> GPU range candidate -> proof.

CPU: nonce tail, streamed commitments, V2/V3 seeds, references and Merkle proof.
GPU: deterministic noise, integer tile scan, transcript/digest and target queue.
Official pinned CPU verifier is an external correctness oracle on the rig.
No pool connection/submission, full production nonce search or performance claim.
"""
import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.constant_merkle import constant_opening
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern
from reference.plain_proof import Opening,PlainProof
from reference.pool_nonce import nonce_tail
from reference.seeds import dense_noise_seeds
from reference.tile_ranges import PatternDomain,RangePlan,RangeCursor,RangeBatch,run_range
from tools.check_range_scan_gpu import ConstantProfile,RangeBackend
from tools.check_tile_scan_gpu import TileQuery,TileScanner,query_reference

# A deliberately easy, NON-saturating synthetic target. Pinned proof_utils.rs:
# 0x1e100000 decodes to 2^236; rank128 has neutral penalty. 8*8*4096=2^18,
# so the scaled bound is 2^254 (roughly one quarter of uniformly random digests).
# This fixed test profile is not a general pool target/configuration decoder.
M=N=128;K=4096;RANK=128;NBITS=0x1e100000
PATTERN=PeriodicPattern.from_list([0,1,8,9,64,65,72,73])
BOUND=(1<<236)*PATTERN.size*PATTERN.size*K


@dataclass(frozen=True)
class SyntheticJob:
    header:bytes
    cert_version:int

    def __post_init__(self):
        if (type(self.header)is not bytes or len(self.header)!=76
            or struct.unpack_from('<I',self.header,72)[0]!=NBITS
            or type(self.cert_version)is not int or self.cert_version not in (2,3)):
            raise ValueError('unsupported synthetic job; never infer a live version/target')

    @property
    def config(self):return struct.pack('<IHH',K,RANK,0)+PATTERN.encoded*2+bytes(32)

    @property
    def job_key(self):return small_hash(self.header+self.config)

    def plan(self):return RangePlan(PatternDomain(M,PATTERN),PatternDomain(N,PATTERN))


def make_job(seed,version):
    if type(seed)is not bytes or len(seed)!=32:raise ValueError('synthetic job seed must be 32 bytes')
    header=(struct.pack('<I',0)+hashlib.sha256(seed+b'/previous').digest()
            +hashlib.sha256(seed+b'/merkle').digest()+struct.pack('<II',0x66666666,NBITS))
    return SyntheticJob(header,version)


@dataclass(frozen=True)
class BaseCommitment:
    job_key:bytes
    opening:Opening


def prepare_base(job):
    return BaseCommitment(job.job_key,constant_opening(job.job_key,64,N*K//1024,[0],K))


@dataclass(frozen=True)
class NonceContext:
    job:SyntheticJob
    worker:bytes
    miner:bytes
    generation:int
    root_a:bytes
    base:BaseCommitment
    profile:ConstantProfile


def prepare_nonce(job,base,worker,miner,generation):
    if type(generation)is not int or not 0<=generation<=0xffffffffffffffff:
        raise ValueError('nonce generation must be u64')
    if base.job_key!=job.job_key or base.opening.total_leaves!=N*K//1024 or base.opening.rows!=[0]:
        raise ValueError('base commitment belongs to a different job/profile')
    base.opening.verify(job.job_key)
    tail=nonce_tail(worker,miner)
    opening=constant_opening(job.job_key,64,M*K//1024,[0],K,tail=tail)
    bs,ass=dense_noise_seeds(job.job_key,opening.root,base.opening.root,M,N,cert_version=job.cert_version)
    profile=ConstantProfile(M,N,K,RANK,64,tail,ass,bs)
    return NonceContext(job,worker,miner,generation,opening.root,base,profile)


@dataclass(frozen=True)
class FoundTile:
    generation:int
    tile:int
    digest:bytes


def find_candidate(context,device=None):
    """Stop at first completed batch containing a target-meeting candidate."""
    plan=context.job.plan();cursor=RangeCursor(context.generation,0,plan.count)
    current=[context.generation];found=[]
    def deliver(records):
        if records and not found:
            tile,digest,generation=records[0]
            found.append(FoundTile(generation,tile,digest))
            current[0]=context.generation^1 # Internal bounded-search stop, not a pool job change.
    backend=RangeBackend(context.profile,device,bound=BOUND)
    try:
        run_range(plan,cursor,backend,lambda:current[0],deliver)
    finally:backend.close()
    return (found[0]if found else None),cursor


def build_candidate(context,found):
    if (found.generation!=context.generation or type(found.digest)is not bytes
        or len(found.digest)!=32 or int.from_bytes(found.digest,'little')>BOUND):
        raise ValueError('stale or target-failing nonce candidate')
    rows,cols=context.job.plan().indices(found.tile)
    batch=RangeBatch(found.tile,found.tile+1,rows,cols,
                     ((tuple(range(len(rows))),tuple(range(len(cols)))),))
    matrix=context.profile.case(batch).matrix()
    words,digest=query_reference(matrix,[TileQuery(*batch.maps[0])])[0]
    if digest!=found.digest:raise ValueError('candidate math belongs to a different nonce/job')
    if nonce_tail(context.worker,context.miner)!=context.profile.tail:
        raise ValueError('nonce tail binding differs')
    key=context.job.job_key
    a=constant_opening(key,64,M*K//1024,list(rows),K,tail=context.profile.tail)
    b=constant_opening(key,64,N*K//1024,list(cols),K)
    if a.root!=context.root_a or b.root!=context.base.opening.root:
        raise ValueError('candidate commitment root binding differs')
    bs,ass=dense_noise_seeds(key,a.root,b.root,M,N,cert_version=context.job.cert_version)
    if (ass,bs)!=(context.profile.seed_a,context.profile.seed_b):
        raise ValueError('candidate seed derivation binding differs')
    for values in (rows,cols):
        if PeriodicPattern.from_list([v-values[0]for v in values])!=PATTERN:
            raise ValueError('candidate pattern differs from job configuration')
    raw=PlainProof(M,N,K,RANK,a,b).serialize();decoded=PlainProof.parse(raw)
    if decoded.serialize()!=raw:raise ValueError('proof encoding round-trip differs')
    decoded.a.verify(key);decoded.bt.verify(key)
    return raw,words


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle',type=Path,help='existing pinned official CPU verifier')
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/tile-scan-sm120.cubin')
    parser.add_argument('--output-dir',type=Path,required=True,help='new local run directory')
    parser.add_argument('--cpu-only',action='store_true',help='development preparation; never reported as GPU work')
    parser.add_argument('--seed',help='optional synthetic 32-byte seed as hex')
    args=parser.parse_args()
    oracle=args.oracle.resolve()if args.oracle else None
    if (not args.cpu_only and oracle is None)or (oracle and (not oracle.is_file()or not os.access(oracle,os.X_OK))):
        raise ValueError('existing official oracle executable is required for the GPU integration check')
    if args.output_dir.exists():raise ValueError('output directory already exists')
    seed=bytes.fromhex(args.seed)if args.seed else secrets.token_bytes(32)
    if len(seed)!=32:raise ValueError('seed must contain 32 bytes')
    args.output_dir.mkdir(parents=True,exist_ok=False);out=args.output_dir.resolve()
    device=None;entries=[]
    try:
        if not args.cpu_only:
            device=TileScanner();device.start(args.cubin)
        base=None
        for version in (2,3):
            job=make_job(seed,version)
            print(f'V{version}: CPU commitment and nonce-bound seed preparation for a fresh synthetic job...',flush=True)
            if base is None or base.job_key!=job.job_key:base=prepare_base(job)
            worker=hashlib.sha256(seed+b'/worker').digest()[:8]
            found=None
            for attempt in range(3):
                miner=hashlib.sha256(seed+b'/miner/'+bytes([version,attempt])).digest()[:8]
                context=prepare_nonce(job,base,worker,miner,version*4+attempt)
                found,cursor=find_candidate(context,device)
                if found:break
            if found is None:raise RuntimeError('bounded synthetic nonce attempts found no candidate')
            label='CPU-ONLY'if args.cpu_only else 'PASS'
            print(f'{label}: V{version} range candidate meets the nonce-bound synthetic target; scanned {cursor.next_tile} tiles',flush=True)
            proof,words=build_candidate(context,found)
            value={'cert_version':version,'header_base64':base64.b64encode(job.header).decode(),
                   'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None,
                   'provenance':{'scope':'fresh synthetic offline nonce/range proof; no pool verdict',
                                 'synthetic_seed_hex':seed.hex(),'worker_nonce':context.worker.hex(),
                                 'miner_nonce':context.miner.hex(),'generation':context.generation,
                                 'tile_id':found.tile}}
            path=out/f'nonce-proof-v{version}.json';path.write_text(json.dumps(value,indent=2)+'\n')
            if oracle:
                subprocess.run([str(oracle),'verify',str(path)],check=True,timeout=120,
                               env=dict(os.environ,RAYON_NUM_THREADS='2'))
                print(f'PASS: V{version} fresh nonce -> range candidate -> independent proof accepted by official offline verifier',flush=True)
            else:print(f'CPU-ONLY: V{version} proof prepared; official verifier not run',flush=True)
            entries.append({'cert_version':version,'gpu_checked':not args.cpu_only,
                            'official_cpu_verifier':'passed'if oracle else 'not run',
                            'tiles_scanned':cursor.next_tile,'proof_bytes':len(proof),
                            'proof_sha256':hashlib.sha256(proof).hexdigest(),
                            'nonce_generation':context.generation,'tile_id':found.tile})
    finally:
        if device:device.close()
    manifest={'complete':True,'gpu_checked':not args.cpu_only,
              'official_cpu_verifier':'passed'if oracle else 'not run','versions':entries,
              'synthetic_seed_hex':seed.hex(),
              'scope':'fresh synthetic offline nonce/range proof integration; no pool connection, share submission or performance claim'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('OFFLINE COMPLETE: fresh nonce commitments/seeds -> range candidate -> independent proof'+(' -> official CPU verification'if oracle else '; official verification NOT RUN'),flush=True)
    print('CPU commitments/seed derivation; '+('CPU-only math'if args.cpu_only else 'GPU noise/tile search')+'. No pool submission or performance claim.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError)as error:
        print('FAIL:',error);raise SystemExit(1)
