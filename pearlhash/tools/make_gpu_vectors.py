"""Create compact pre-noised GPU math inputs; never encode a pool job.

Binary: PHGPU01 NUL; LE u32 rows,cols,k,rank; LE i32 A and B-transposed;
16 LE u32 expected transcript words. JSON originals remain authoritative.
Run from pearlhash/: python3 -m tools.make_gpu_vectors tests/vectors tests/gpu
"""
import json
from pathlib import Path
import random
import struct
import sys
from reference.dense import jackpot, verify_opened_math


def write(path, a, bt, rank, expected):
    rows, cols, k = len(a), len(bt), len(a[0])
    assert all(len(row) == k for row in a + bt)
    assert jackpot(a, bt, rank) == expected
    data = b'PHGPU01\0' + struct.pack('<4I', rows, cols, k, rank)
    for row in a + bt:
        data += struct.pack(f'<{k}i', *row)
    path.write_bytes(data + struct.pack('<16I', *expected))


def main(source, dest):
    dest.mkdir(parents=True, exist_ok=True)
    for version in (2, 3):
        fixture = json.loads((source / f'official-v{version}.json').read_text())
        verify_opened_math(fixture)
        a = [[x+n for x, n in zip(row, noise, strict=True)]
             for row, noise in zip(fixture['opened_a'], fixture['noise_a'], strict=True)]
        bt = [[x+n for x, n in zip(row, noise, strict=True)]
              for row, noise in zip(fixture['opened_bt'], fixture['noise_bt'], strict=True)]
        write(dest / f'official-v{version}.bin', a, bt, fixture['rank'], fixture['jackpot_u32'])
    rng = random.Random(5060)
    for name, rows, cols, k, rank in [
        ('signed-reuse', 3, 5, 4096, 128),
        ('single-negative', 1, 1, 32, 32),
        ('multi-block', 17, 9, 1024, 32),
        ('max-pairs', 32, 32, 32, 32),
        ('zeros', 2, 3, 1024, 32),
    ]:
        a = [[rng.randint(-127,127) for _ in range(k)] for _ in range(rows)]
        bt = [[rng.randint(-127,127) for _ in range(k)] for _ in range(cols)]
        if name == 'single-negative':
            a, bt = [[-127]*k], [[127]*k]
        if name == 'zeros':
            a = [[0]*k for _ in range(rows)]
        write(dest / f'{name}.bin', a, bt, rank, jackpot(a, bt, rank))


if __name__ == '__main__':
    main(*map(Path, sys.argv[1:]))
