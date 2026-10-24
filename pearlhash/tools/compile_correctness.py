"""Build native sm_120 cubin with NVRTC 12.9, without a GPU or CUDA headers.

Usage: python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 output.cubin
Optional third argument selects a source file in gpu/, e.g. nonce_tail.cu.
Compiler dependencies are development-host-only; not shipped to the rig.
"""
import ctypes as C
from pathlib import Path
import sys


def build(library, output, source_name='correctness.cu'):
    lib = C.CDLL(library)
    lib.nvrtcCreateProgram.argtypes = [C.POINTER(C.c_void_p), C.c_char_p, C.c_char_p,
                                     C.c_int, C.c_void_p, C.c_void_p]
    lib.nvrtcCompileProgram.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_char_p)]
    lib.nvrtcDestroyProgram.argtypes = [C.POINTER(C.c_void_p)]
    for name in ['nvrtcGetProgramLogSize', 'nvrtcGetCUBINSize']:
        getattr(lib, name).argtypes = [C.c_void_p, C.POINTER(C.c_size_t)]
    for name in ['nvrtcGetProgramLog', 'nvrtcGetCUBIN']:
        getattr(lib, name).argtypes = [C.c_void_p, C.c_void_p]
    major, minor = C.c_int(), C.c_int()
    lib.nvrtcVersion(C.byref(major), C.byref(minor))
    print(f'NVRTC {major.value}.{minor.value}; native sm_120; GPU not used')
    program = C.c_void_p()
    source = (Path(__file__).parents[1] / 'gpu' / source_name).read_bytes()
    header = (Path(__file__).parents[1] / 'gpu/keyed64.h').read_bytes()
    headers = (C.c_char_p * 1)(header)
    names = (C.c_char_p * 1)(b'keyed64.h')
    rc = lib.nvrtcCreateProgram(C.byref(program), source, source_name.encode(), 1, headers, names)
    if rc:
        raise RuntimeError(f'nvrtcCreateProgram: {rc}')
    try:
        options = (C.c_char_p * 2)(b'--gpu-architecture=sm_120', b'--std=c++17')
        rc = lib.nvrtcCompileProgram(program, len(options), options)
        size = C.c_size_t()
        lib.nvrtcGetProgramLogSize(program, C.byref(size))
        log = C.create_string_buffer(size.value)
        lib.nvrtcGetProgramLog(program, log)
        print(log.value.decode())
        if rc:
            raise RuntimeError(f'nvrtcCompileProgram: {rc}')
        rc = lib.nvrtcGetCUBINSize(program, C.byref(size))
        if rc:
            raise RuntimeError(f'nvrtcGetCUBINSize: {rc}')
        cubin = C.create_string_buffer(size.value)
        rc = lib.nvrtcGetCUBIN(program, cubin)
        if rc:
            raise RuntimeError(f'nvrtcGetCUBIN: {rc}')
        Path(output).write_bytes(cubin.raw)
        print(f'Wrote {size.value} bytes')
    finally:
        lib.nvrtcDestroyProgram(C.byref(program))


if __name__ == '__main__':
    build(*sys.argv[1:])
