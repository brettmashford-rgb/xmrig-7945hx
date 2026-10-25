#!/usr/bin/env python3
"""Reproduce sm_120 readable PTX with development-host NVRTC 12.9.86. ISC.

No compiler/toolkit is required by the rig installer. Supply an existing NVRTC
library explicitly; this build helper never downloads or installs dependencies.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nvrtc',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',default='warp_tile_scan.cu')
    parser.add_argument('--entry',default='warp_virtual_tile_scan')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    lib=C.CDLL(str(args.nvrtc.resolve()))
    def bind(name,types):
        f=getattr(lib,name);f.argtypes=types;f.restype=C.c_int;return f
    version=bind('nvrtcVersion',[C.POINTER(C.c_int),C.POINTER(C.c_int)])
    major=C.c_int();minor=C.c_int();assert version(C.byref(major),C.byref(minor))==0
    if(major.value,minor.value)!=(12,9):raise RuntimeError('NVRTC 12.9 required')
    create=bind('nvrtcCreateProgram',[C.POINTER(C.c_void_p),C.c_char_p,C.c_char_p,C.c_int,C.c_void_p,C.c_void_p])
    compile=bind('nvrtcCompileProgram',[C.c_void_p,C.c_int,C.POINTER(C.c_char_p)])
    getlogsize=bind('nvrtcGetProgramLogSize',[C.c_void_p,C.POINTER(C.c_size_t)])
    getlog=bind('nvrtcGetProgramLog',[C.c_void_p,C.c_void_p])
    getsize=bind('nvrtcGetPTXSize',[C.c_void_p,C.POINTER(C.c_size_t)])
    getptx=bind('nvrtcGetPTX',[C.c_void_p,C.c_void_p])
    destroy=bind('nvrtcDestroyProgram',[C.POINTER(C.c_void_p)])
    program=C.c_void_p();source_path=root/'gpu'/args.source;source=source_path.read_bytes()
    if create(C.byref(program),source,source_path.name.encode(),0,None,None):raise RuntimeError('NVRTC create failed')
    try:
        options=[b'--gpu-architecture=compute_120',b'--std=c++17',('-I'+str(root/'gpu')).encode()]
        rc=compile(program,len(options),(C.c_char_p*len(options))(*options))
        size=C.c_size_t();getlogsize(program,C.byref(size));log=C.create_string_buffer(size.value);getlog(program,log)
        if log.value:print(log.value.decode())
        if rc:raise RuntimeError('NVRTC compilation failed: '+str(rc))
        if getsize(program,C.byref(size)):raise RuntimeError('NVRTC PTX size failed')
        buffer=C.create_string_buffer(size.value)
        if getptx(program,buffer):raise RuntimeError('NVRTC PTX retrieval failed')
        raw=buffer.raw[:-1];raw.decode('utf-8')
        marker=('.visible .entry '+args.entry+'(').encode()
        if b'.target sm_120'not in raw or marker not in raw:
            raise RuntimeError('unexpected PTX target or entry')
        entry=raw.split(marker,1)[1]
        if b'bar.sync'in entry:raise RuntimeError('new warp entry contains a block barrier')
        args.output.write_bytes(raw)
        print(json.dumps({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'warp_entry_block_barriers':0}))
    finally:destroy(C.byref(program))
    return 0


if __name__=='__main__':raise SystemExit(main())
