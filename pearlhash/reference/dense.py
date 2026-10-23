"""Independent scalar dense math check against official-generated fixtures.

Algorithm sources at pinned upstream commit: circuit/pearl_noise.rs,
ffi/mine.rs and api/proof_utils.rs. This does NOT authenticate Merkle openings,
decode a pool job, or implement the full consensus sanity/target checks.
Use the pinned Rust oracle for complete PlainProof verification.
"""
import base64
import struct
try:
    from blake3 import blake3
except ImportError:
    from reference.native_hash import blake3
from reference.seeds import dense_noise_seeds


def _random_hash(index: int, label: bytes, key: bytes, slot: int) -> bytes:
    message = bytearray(64)
    struct.pack_into('<I', message, slot * 4, index + 1)
    message[32:] = label.ljust(32, b'\0')
    return blake3(message, key=key).digest()


def noise_rows(k: int, rank: int, indices: list[int], label: bytes, key: bytes) -> list[list[int]]:
    """Compute selected noise rows, treating B as transposed columns."""
    if rank < 32 or rank > 1024 or rank & (rank - 1) or k <= 0:
        raise ValueError('unsupported noise dimensions')
    permutation = []
    for block in range((k + 7) // 8):
        for value in struct.unpack('<8I', _random_hash(block, label, key, 1)):
            first = value & (rank - 1)
            second = first ^ (1 + (((rank - 1) * value) >> 32))
            permutation.append((first, second))
    rows = []
    for index in indices:
        if type(index) is not int or index < 0:
            raise ValueError('invalid selected index')
        start = index * rank
        uniform = []
        for block in range(start // 32, (start + rank + 31) // 32):
            raw = _random_hash(block, label, key, 0)
            for offset, value in enumerate(raw):
                if start <= block * 32 + offset < start + rank:
                    uniform.append((value & 63) - 32)
        rows.append([uniform[a] - uniform[b] for a, b in permutation[:k]])
    return rows


def jackpot(a: list[list[int]], bt: list[list[int]], rank: int) -> list[int]:
    """Compute cumulative integer products and the 16-word rank-boundary fold."""
    if not a or not bt or rank <= 0:
        raise ValueError('empty tile or invalid rank')
    k = len(a[0])
    if any(len(row) != k for row in a + bt) or k % rank:
        raise ValueError('inconsistent tile dimensions')
    accumulators = [[0 for _ in bt] for _ in a]
    transcript = [0] * 16
    for end in range(rank, k + 1, rank):
        folded = 0
        for u, row in enumerate(a):
            for v, col in enumerate(bt):
                accumulators[u][v] += sum(row[l] * col[l] for l in range(end - rank, end))
                if not -(1 << 31) <= accumulators[u][v] < (1 << 31):
                    raise ValueError('int32 accumulation overflow')
                folded ^= accumulators[u][v] & 0xFFFFFFFF
        idx = (end // rank - 1) % 16
        previous = transcript[idx]
        rotated = ((previous << 13) | (previous >> 19)) & 0xFFFFFFFF
        transcript[idx] = rotated ^ folded
    return transcript


def verify_opened_math(fixture: dict) -> None:
    """Compare independent math with official-generated intermediate outputs.

    A successful check is not proof verification or pool acceptance.
    """
    header = base64.b64decode(fixture['header_base64'], validate=True)
    config = base64.b64decode(fixture['config_base64'], validate=True)
    if len(header) != 76 or len(config) != 52:
        raise ValueError('unexpected header/config length')
    job_key = blake3(header + config).digest()
    if job_key != bytes(fixture['job_key']):
        raise ValueError('job key mismatch')
    b_seed, a_seed = dense_noise_seeds(
        job_key, bytes(fixture['root_a']), bytes(fixture['root_bt']),
        fixture['m'], fixture['n'], cert_version=fixture['cert_version'],
    )
    if a_seed != bytes(fixture['a_noise_seed']) or b_seed != bytes(fixture['b_noise_seed']):
        raise ValueError('noise seed mismatch')
    k, rank = fixture['k'], fixture['rank']
    noise_a = noise_rows(k, rank, fixture['a_rows'], b'A_tensor', a_seed)
    noise_bt = noise_rows(k, rank, fixture['b_cols'], b'B_tensor', b_seed)
    if noise_a != fixture['noise_a'] or noise_bt != fixture['noise_bt']:
        raise ValueError('noise matrix mismatch')
    signals_a, signals_bt = fixture['opened_a'], fixture['opened_bt']
    if len(signals_a) != len(noise_a) or len(signals_bt) != len(noise_bt):
        raise ValueError('selected row count mismatch')
    if any(len(row) != k for row in signals_a + signals_bt):
        raise ValueError('signal width mismatch')
    if any(not -64 <= value <= 64 for row in signals_a + signals_bt for value in row):
        raise ValueError('signal outside official range')
    a = [[x + n for x, n in zip(row, noise, strict=True)] for row, noise in zip(signals_a, noise_a, strict=True)]
    bt = [[x + n for x, n in zip(row, noise, strict=True)] for row, noise in zip(signals_bt, noise_bt, strict=True)]
    words = jackpot(a, bt, rank)
    if words != fixture['jackpot_u32']:
        raise ValueError('jackpot transcript mismatch')
    digest = blake3(struct.pack('<16I', *words), key=a_seed).digest()
    if digest != bytes(fixture['jackpot_hash']):
        raise ValueError('jackpot digest mismatch')
