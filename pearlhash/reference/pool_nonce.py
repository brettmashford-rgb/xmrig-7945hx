"""Independent observed Pearlhash nonce-to-signal-tail mapping. ISC license.

Wire nonce fields are decoded as eight bytes each, preserving their byte order.
This primitive alone does not establish full matrix reconstruction or a share.
"""
from reference.native_hash import small_hash


def nonce_tail(worker_nonce, miner_nonce):
    for value in (worker_nonce, miner_nonce):
        if type(value) is not bytes or len(value) != 8:
            raise ValueError('nonce must be exactly eight bytes')
    digest = small_hash(worker_nonce + miner_nonce)
    return bytes(((value % 129) - 64) & 255 for value in digest[:16])
