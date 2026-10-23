"""Generate PHGPU02 tests: PHGPU01 data with magic changed, followed by
LE seeds A/B (8 words each), A/B indices, signal A/B (i32), expected digest.
Expected noise/transcripts/digests come from Python blake3/reference code.
"""
import json
from pathlib import Path
import random
import struct
import sys
from blake3 import blake3
from reference.dense import noise_rows, jackpot, verify_opened_math
from tools.make_gpu_vectors import write


def emit(path, signals_a, signals_b, ia, ib, k, rank, seed_a, seed_b,
         official_words=None, official_digest=None):
    na=noise_rows(k,rank,ia,b'A_tensor',seed_a)
    nb=noise_rows(k,rank,ib,b'B_tensor',seed_b)
    a=[[x+n for x,n in zip(s,noise,strict=True)] for s,noise in zip(signals_a,na,strict=True)]
    bt=[[x+n for x,n in zip(s,noise,strict=True)] for s,noise in zip(signals_b,nb,strict=True)]
    words=jackpot(a,bt,rank)
    digest=blake3(struct.pack('<16I',*words),key=seed_a).digest()
    if official_words is not None:
        assert words==official_words and digest==official_digest
    write(path,a,bt,rank,words)
    data=b'PHGPU02\0'+path.read_bytes()[8:]+seed_a+seed_b
    data+=struct.pack(f'<{len(ia)+len(ib)}I',*ia,*ib)
    for row in signals_a+signals_b:
        data+=struct.pack(f'<{k}i',*row)
    path.write_bytes(data+digest)


def main(source,dest):
    dest.mkdir(parents=True,exist_ok=True)
    for version in (2,3):
        f=json.loads((source/f'official-v{version}.json').read_text())
        verify_opened_math(f)
        emit(dest/f'official-v{version}.bin',f['opened_a'],f['opened_bt'],f['a_rows'],f['b_cols'],
             f['k'],f['rank'],bytes(f['a_noise_seed']),bytes(f['b_noise_seed']),
             f['jackpot_u32'],bytes(f['jackpot_hash']))
    rng=random.Random(506004)
    for name,ia,ib,k,rank in [
        ('rank32', [0,31,32], [3,1], 1056,32),
        ('rank1024', [4194303,0], [65537,4,2], 2048,1024),
        ('repeated-indices', [17,17,2], [2,0,2], 2176,128),
    ]:
        a=[[rng.randint(-64,64) for _ in range(k)] for _ in ia]
        bt=[[rng.randint(-64,64) for _ in range(k)] for _ in ib]
        emit(dest/f'{name}.bin',a,bt,ia,ib,k,rank,rng.randbytes(32),rng.randbytes(32))


if __name__=='__main__':
    main(*map(Path,sys.argv[1:]))
