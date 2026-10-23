"""Fresh independent dense candidate -> GPU math check -> PlainProof -> oracle.

SYNTHETIC OFFLINE JOBS ONLY. No pool connection, submission or live-miner claim.
Uses SHAKE256 to generate signal randomness, not to replace the Pearl algorithm.
Run from pearlhash/: python3 -S -m tools.offline_end_to_end --oracle PATH ...
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
from reference.dense import noise_rows,jackpot
from reference.seeds import dense_noise_seeds
from reference.native_hash import small_hash
from reference.plain_proof import PlainProof,Tree
from reference.patterns import PeriodicPattern

BASE=Path(__file__).resolve().parents[1]
ROWS=[0,1,8,9,64,65,72,73]


def signal_bytes(seed,label,count):
    raw=hashlib.shake_256(seed+label).digest(count*3)
    # Rejection sampling: all 129 allowed signal values have equal probability.
    result=bytes((v-64)&255 for v in raw if v<129)[:count]
    if len(result)!=count:raise ValueError('insufficient deterministic random stream')
    return result


def selected_rows(raw,rows,k):
    return [[v if v<128 else v-256 for v in raw[i*k:(i+1)*k]] for i in rows]


def candidate(seed,version):
    if version not in (2,3):raise ValueError('explicit V2/V3 required')
    seed=hashlib.sha256(seed+struct.pack('<I',version)).digest()
    m=n=128;k=4096 if version==3 else 2048;rank=128
    # Synthetic header with deliberately easy offline nBits; never a pool job.
    header=(struct.pack('<I',0)+hashlib.sha256(seed+b'prev').digest()
            +hashlib.sha256(seed+b'merkle').digest()+struct.pack('<II',0x66666666,0x207fffff))
    pattern=PeriodicPattern.from_list(ROWS).encoded
    config=struct.pack('<IHH',k,rank,0)+pattern+pattern+bytes(32)
    job_key=small_hash(header+config)
    raw_a=signal_bytes(seed,b'A',m*k);raw_b=signal_bytes(seed,b'BT',n*k)
    tree_a=Tree(raw_a,job_key);tree_b=Tree(raw_b,job_key)
    b_seed,a_seed=dense_noise_seeds(job_key,tree_a.root,tree_b.root,m,n,cert_version=version)
    sa=selected_rows(raw_a,ROWS,k);sb=selected_rows(raw_b,ROWS,k)
    na=noise_rows(k,rank,ROWS,b'A_tensor',a_seed)
    nb=noise_rows(k,rank,ROWS,b'B_tensor',b_seed)
    a=[[x+y for x,y in zip(s,no,strict=True)] for s,no in zip(sa,na,strict=True)]
    bt=[[x+y for x,y in zip(s,no,strict=True)] for s,no in zip(sb,nb,strict=True)]
    words=jackpot(a,bt,rank);digest=small_hash(struct.pack('<16I',*words),a_seed)
    gpu=b'PHGPU02\0'+struct.pack('<4I',len(ROWS),len(ROWS),k,rank)
    for row in a+bt:gpu+=struct.pack(f'<{k}i',*row)
    gpu+=struct.pack('<16I',*words)+a_seed+b_seed+struct.pack('<16I',*(ROWS+ROWS))
    for row in sa+sb:gpu+=struct.pack(f'<{k}i',*row)
    gpu+=digest
    return {'header':header,'config':config,'job_key':job_key,'tree_a':tree_a,'tree_b':tree_b,
            'gpu_input':gpu,'digest':digest,'m':m,'n':n,'k':k,'rank':rank}


def build_proof(c):
    a=c['tree_a'].opening(ROWS,c['k']);bt=c['tree_b'].opening(ROWS,c['k'])
    a.verify(c['job_key']);bt.verify(c['job_key'])
    return PlainProof(c['m'],c['n'],c['k'],c['rank'],a,bt).serialize()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--gpu-check',type=Path,default=BASE/'bin/pearl-gpu-check')
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/correctness-sm120.cubin')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--versions',type=int,nargs='+',choices=(2,3),default=[2,3])
    parser.add_argument('--seed',help='optional 64 hex digits, for reproducible offline tests')
    parser.add_argument('--cpu-only',action='store_true',help='development-host mode; no GPU validation')
    args=parser.parse_args()
    seed=bytes.fromhex(args.seed) if args.seed else secrets.token_bytes(32)
    if len(seed)!=32:raise ValueError('seed must be 32 bytes')
    oracle=args.oracle.resolve()
    if not oracle.is_file():raise ValueError('official CPU oracle executable not found')
    args.output_dir.mkdir(parents=True,exist_ok=False)
    out=args.output_dir.resolve();env=dict(os.environ,RAYON_NUM_THREADS='2')
    manifest={'scope':'synthetic offline; no pool verdict','seed_hex':seed.hex(),
              'gpu_math_checked':not args.cpu_only,'python':sys.version,'versions':[]}
    for version in args.versions:
        print(f'V{version}: building fresh independent matrices and commitments...',flush=True)
        c=candidate(seed,version);gpu=out/f'candidate-v{version}.bin';gpu.write_bytes(c['gpu_input'])
        if args.cpu_only:
            print('CPU-ONLY: GPU stage skipped on development host',flush=True)
        else:
            subprocess.run([str(args.gpu_check.resolve()),str(args.cubin.resolve()),str(gpu)],
                           check=True,timeout=120)
        # Only build/emit the PlainProof after the requested GPU math stage passes.
        proof=build_proof(c)
        value={'cert_version':version,'header_base64':base64.b64encode(c['header']).decode(),
               'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':None,
               'provenance':{'generator':'independent SHAKE256 signals + BLAKE3 commitments + Merkle openings',
                             'scope':'synthetic offline; not official try_mine_one; not pool acceptance'}}
        path=out/f'independent-proof-v{version}.json';path.write_text(json.dumps(value,indent=2)+'\n')
        subprocess.run([str(oracle),'verify',str(path)],check=True,timeout=120,env=env)
        manifest['versions'].append({'version':version,'proof_bytes':len(proof),
                                    'proof_sha256':hashlib.sha256(proof).hexdigest(),
                                    'gpu_input_sha256':hashlib.sha256(c['gpu_input']).hexdigest(),
                                    'root_a':c['tree_a'].root.hex(),'root_bt':c['tree_b'].root.hex(),
                                    'jackpot_digest':c['digest'].hex(),'official_verifier':'passed'})
        print(f'PASS: independently constructed V{version} PlainProof accepted by official offline verifier',flush=True)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('OFFLINE COMPLETE: '+('CPU only' if args.cpu_only else 'GPU math + independent proof + official verification'),flush=True)
    print('No pool connection, submitted share, pool verdict or performance claim.',flush=True)


if __name__=='__main__':main()
