"""Development-only NVRTC build; the rig receives compiled PTX. ISC."""
import ctypes as C
from pathlib import Path
import sys,hashlib

def build(library,output):
    base=Path(__file__).resolve().parents[1];lib=C.CDLL(library)
    lib.nvrtcCreateProgram.argtypes=[C.POINTER(C.c_void_p),C.c_char_p,C.c_char_p,C.c_int,C.c_void_p,C.c_void_p]
    lib.nvrtcCompileProgram.argtypes=[C.c_void_p,C.c_int,C.POINTER(C.c_char_p)]
    lib.nvrtcDestroyProgram.argtypes=[C.POINTER(C.c_void_p)]
    for name in('nvrtcGetProgramLogSize','nvrtcGetPTXSize'):getattr(lib,name).argtypes=[C.c_void_p,C.POINTER(C.c_size_t)]
    for name in('nvrtcGetProgramLog','nvrtcGetPTX'):getattr(lib,name).argtypes=[C.c_void_p,C.c_void_p]
    program=C.c_void_p();source=base/'gpu/projected_scan.cu'
    if lib.nvrtcCreateProgram(C.byref(program),source.read_bytes(),source.name.encode(),0,None,None):raise RuntimeError('NVRTC program creation failed')
    try:
        opts=(C.c_char_p*3)(b'--gpu-architecture=compute_120',b'--std=c++17',('-I'+str(base/'gpu')).encode())
        rc=lib.nvrtcCompileProgram(program,len(opts),opts);size=C.c_size_t()
        lib.nvrtcGetProgramLogSize(program,C.byref(size));log=C.create_string_buffer(size.value);lib.nvrtcGetProgramLog(program,log)
        if log.value:print(log.value.decode())
        if rc:raise RuntimeError('NVRTC compilation failed: '+str(rc))
        lib.nvrtcGetPTXSize(program,C.byref(size));buf=C.create_string_buffer(size.value)
        if lib.nvrtcGetPTX(program,buf):raise RuntimeError('NVRTC PTX readback failed')
        raw=buf.raw.removesuffix(b'\0');output=Path(output)
        if output.exists()and output.read_bytes()!=raw:raise RuntimeError('existing PTX differs; refusing overwrite')
        output.write_bytes(raw);print(len(raw),hashlib.sha256(raw).hexdigest())
    finally:lib.nvrtcDestroyProgram(C.byref(program))

if __name__=='__main__':build(*sys.argv[1:])
