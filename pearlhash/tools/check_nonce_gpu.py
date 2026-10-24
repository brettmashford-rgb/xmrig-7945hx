#!/usr/bin/env python3
"""Offline nonce-tail GPU correctness test. ISC license. No network/mining.

Compares native sm_120 outputs with the separate CPU BLAKE3 implementation.
The prior GPU math cubin, services and clocks are not changed or exercised.
"""
import argparse
import ctypes as C
from pathlib import Path
import random
import struct
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from reference.pool_nonce import nonce_tail


def cases():
    # Seven boundary inputs plus 256 reproducible synthetic pairs; deliberately
    # not a multiple of a 128-thread launch block.
    values = [(0, 0), (0xffffffffffffffff, 0xffffffffffffffff),
              (0, 0xffffffffffffffff), (0xffffffffffffffff, 0),
              (0x0123456789abcdef, 0xffffffff),
              (0x0123456789abcdef, 0x100000000),
              (0x0123456789abcdef, 0xfffffffffffffffe)]
    rng = random.Random(506008)
    values += [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(256)]
    inputs = [struct.pack('<QQ', worker, nonce) for worker, nonce in values]
    expected = b''.join(nonce_tail(value[:8], value[8:]) for value in inputs)
    return b''.join(inputs), expected


from tools.cuda_driver import CudaDevice


class Device(CudaDevice):
    def run(self, inputs, expected):
        count = C.c_uint(len(inputs)//16)
        source = self.allocate(inputs)
        # Guard both ends of the output, and poison all expected output bytes.
        destination = self.allocate(b'\xa5'*(len(expected)+32))
        interior = C.c_ulonglong(destination.value+16)
        function = C.c_void_p()
        self.api('cuModuleGetFunction', [C.POINTER(C.c_void_p), C.c_void_p, C.c_char_p],
                 C.byref(function), self.module, b'nonce_tail')
        arguments = (C.c_void_p*3)(*(C.cast(C.byref(value), C.c_void_p)
                                    for value in (source, interior, count)))
        self.api('cuLaunchKernel', [C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                 function, (count.value+127)//128, 1, 1, 128, 1, 1, 0,
                 None, arguments, None)
        self.api('cuCtxSynchronize', [])
        output = C.create_string_buffer(len(expected)+32)
        self.api('cuMemcpyDtoH_v2', [C.c_void_p, C.c_ulonglong, C.c_size_t],
                 output, destination, len(output))
        if output.raw[:16] != b'\xa5'*16 or output.raw[-16:] != b'\xa5'*16:
            raise RuntimeError('GPU wrote outside the expected output range')
        if output.raw[16:-16] != expected:
            raise RuntimeError('GPU nonce tails differ from the independent CPU calculation')
        return count.value



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-only', action='store_true')
    parser.add_argument('--cubin', type=Path, default=BASE/'gpu/nonce-tail-sm120.cubin')
    args = parser.parse_args()
    inputs, expected = cases()
    count = len(inputs)//16
    if args.cpu_only:
        print(f'CPU-ONLY: generated {count} synthetic nonce-tail comparisons; GPU not run')
        return 0
    device = Device()
    try:
        device.start(args.cubin)
        count = device.run(inputs, expected)
        print(f'PASS: GPU nonce-to-tail mapping matches independent CPU calculation ({count} cases)')
        print('PASS: output guards unchanged')
        print('Offline primitive only; full pool reconstruction and custom share acceptance remain unvalidated.')
        return 0
    finally:
        device.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print('FAIL:', error)
        raise SystemExit(1)
