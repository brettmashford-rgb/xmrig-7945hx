"""Build native sm_120 cubin with NVRTC 12.9, without a GPU or CUDA headers.

Usage: python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 output.cubin
Optional third argument selects a source file in gpu/, e.g. nonce_tail.cu.
Optional fourth argument 'ptx' emits readable compute_120 PTX for driver JIT.
Compiler dependencies are development-host-only; not shipped to the rig.
"""
import ctypes as C
from pathlib import Path
import sys


def build(library, output, source_name='correctness.cu', output_format='cubin'):
    if output_format not in ('cubin','ptx'):raise ValueError('output format must be cubin or ptx')
    lib = C.CDLL(library)
    lib.nvrtcCreateProgram.argtypes = [C.POINTER(C.c_void_p), C.c_char_p, C.c_char_p,
                                     C.c_int, C.c_void_p, C.c_void_p]
    lib.nvrtcCompileProgram.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_char_p)]
    lib.nvrtcDestroyProgram.argtypes = [C.POINTER(C.c_void_p)]
    kind='CUBIN'if output_format=='cubin'else 'PTX'
    for name in ['nvrtcGetProgramLogSize', f'nvrtcGet{kind}Size']:
        getattr(lib, name).argtypes = [C.c_void_p, C.POINTER(C.c_size_t)]
    for name in ['nvrtcGetProgramLog', f'nvrtcGet{kind}']:
        getattr(lib, name).argtypes = [C.c_void_p, C.c_void_p]
    major, minor = C.c_int(), C.c_int()
    lib.nvrtcVersion(C.byref(major), C.byref(minor))
    target='sm_120'if output_format=='cubin'else 'compute_120 PTX for driver JIT'
    print(f'NVRTC {major.value}.{minor.value}; {target}; GPU not used')
    program = C.c_void_p()
    source = (Path(__file__).parents[1] / 'gpu' / source_name).read_bytes()
    # The noise/table pipeline includes the existing validated MMA implementation.
    # Supply explicit repository headers; no host CUDA headers/toolkit required.
    include_names = ('keyed64.h', 'mma_correctness.cu', 'noise_mma.cu', 'scan_target.h',
                     'tile_scan_core.cuh', 'tile_scan.cu', 'virtual_input.h')
    headers = (C.c_char_p * len(include_names))(*(
        (Path(__file__).parents[1] / 'gpu' / name).read_bytes() for name in include_names))
    names = (C.c_char_p * len(include_names))(*(name.encode() for name in include_names))
    rc = lib.nvrtcCreateProgram(C.byref(program), source, source_name.encode(), len(include_names), headers, names)
    if rc:
        raise RuntimeError(f'nvrtcCreateProgram: {rc}')
    try:
        architecture=b'--gpu-architecture=sm_120'if output_format=='cubin'else b'--gpu-architecture=compute_120'
        options = (C.c_char_p * 2)(architecture, b'--std=c++17')
        rc = lib.nvrtcCompileProgram(program, len(options), options)
        size = C.c_size_t()
        lib.nvrtcGetProgramLogSize(program, C.byref(size))
        log = C.create_string_buffer(size.value)
        lib.nvrtcGetProgramLog(program, log)
        print(log.value.decode())
        if rc:
            raise RuntimeError(f'nvrtcCompileProgram: {rc}')
        rc = getattr(lib,f'nvrtcGet{kind}Size')(program, C.byref(size))
        if rc:
            raise RuntimeError(f'nvrtcGet{kind}Size: {rc}')
        cubin = C.create_string_buffer(size.value)
        rc = getattr(lib,f'nvrtcGet{kind}')(program, cubin)
        if rc:
            raise RuntimeError(f'nvrtcGet{kind}: {rc}')
        data=cubin.raw
        if output_format=='ptx':data=data.removesuffix(b'\0');data.decode('utf-8')
        Path(output).write_bytes(data)
        print(f'Wrote {len(data)} bytes ({output_format})')
    finally:
        lib.nvrtcDestroyProgram(C.byref(program))


if __name__ == '__main__':
    build(*sys.argv[1:])
