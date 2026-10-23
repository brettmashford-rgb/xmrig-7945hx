"""Dense seed derivation, adapted from Pearl's ISC-licensed reference.

Source: zk-pow/src/api/{seed.rs,proof_utils.rs}, upstream commit
82e6eee7076aafe10123e08db78f100d270c0582. Excludes MoE, matrix hashing,
noise generation, GEMM, jackpot calculation, Merkle proofs and target checks.
"""

import struct

try:
    from blake3 import blake3
except ImportError:
    from reference.native_hash import blake3


def _hash32(value: bytes) -> None:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ValueError("expected exactly 32 bytes")


def _dimension(value: int) -> None:
    if type(value) is not int or not 0 < value <= 0xFFFFFFFF:
        raise ValueError("dimension must be a positive u32")


def _bind_root(root: bytes, dimension: int, label: bytes) -> bytes:
    salt = blake3(label).digest()
    return blake3(root + struct.pack("<I", dimension) + bytes(28), key=salt).digest()


def dense_noise_seeds(
    job_key: bytes, hash_a: bytes, hash_b: bytes, m: int, n: int,
    *, cert_version: int,
) -> tuple[bytes, bytes]:
    """Return (b_noise_seed, a_noise_seed) for explicit certificate V1/V2/V3.

    Inputs hash_a/hash_b are raw matrix commitment roots, not salted roots.
    This validates primitive inputs, not consensus matrix dimensions or a proof.
    """
    for value in (job_key, hash_a, hash_b):
        _hash32(value)
    _dimension(m)
    _dimension(n)
    if type(cert_version) is not int or cert_version not in (1, 2, 3):
        raise ValueError("unsupported certificate version; never guess")
    if cert_version == 3:
        hash_a = _bind_root(hash_a, m, b"pearl/cert-v3/noise-seed/A")
        hash_b = _bind_root(hash_b, n, b"pearl/cert-v3/noise-seed/B")
    b_seed = blake3(job_key + hash_b).digest()
    a_seed = blake3(b_seed + hash_a).digest()
    return b_seed, a_seed
