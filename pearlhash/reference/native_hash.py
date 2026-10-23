"""CPU hash primitives through a small C ABI library, independent of Python ABI.

Runtime makes no connections. Build proof/blake3_cpu.cpp on a development host.
"""
import ctypes as C
import os
from pathlib import Path

_lib=None


def library():
    global _lib
    if _lib is None:
        path=os.environ.get('PEARL_HASH_LIBRARY') or str(Path(__file__).parents[1]/'bin/libpearlhash.so')
        lib=C.CDLL(path)
        lib.ph_hash_small.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p]
        lib.ph_chunk_cvs.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p]
        lib.ph_chunk_value.argtypes=[C.c_void_p,C.c_uint64,C.c_void_p,C.c_void_p]
        lib.ph_parent_cvs.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_int,C.c_void_p]
        _lib=lib
    return _lib


def key_check(key):
    if not isinstance(key,bytes) or len(key)!=32:
        raise ValueError('key must be 32 bytes')


def small_hash(data,key=None):
    if not isinstance(data,(bytes,bytearray,memoryview)) or len(data)>1024:
        raise ValueError('small_hash supports bytes of length 0..1024 only')
    data=bytes(data)
    if key is not None:key_check(key)
    out=C.create_string_buffer(32)
    if library().ph_hash_small(data,len(data),key,out):raise ValueError('native small hash failed')
    return out.raw


class blake3:
    """One-shot 32-byte digest facade for existing 64/128-byte math messages.

    Deliberately not a streaming/XOF BLAKE3 implementation.
    """
    def __init__(self,data=b'',*,key=None):
        self._digest=small_hash(data,key)
    def digest(self):return self._digest


def chunk_cvs(data,key):
    key_check(key)
    if not data or len(data)%1024 or len(data)>64*1024*1024:
        raise ValueError('chunk input must contain 1..65536 complete chunks')
    out=C.create_string_buffer(len(data)//1024*32)
    if library().ph_chunk_cvs(data,len(data)//1024,key,out):raise ValueError('native chunk hash failed')
    raw=out.raw
    return [raw[i:i+32] for i in range(0,len(raw),32)]


def parents(children,key,*,root=False):
    key_check(key)
    if len(children)<2 or len(children)%2 or len(children)>65536 or (root and len(children)!=2):
        raise ValueError('parent inputs must be complete pairs; root requires one pair')
    if any(not isinstance(v,bytes) or len(v)!=32 for v in children):
        raise ValueError('each child chaining value must be 32 bytes')
    out=C.create_string_buffer(len(children)//2*32)
    if library().ph_parent_cvs(b''.join(children),len(children)//2,key,int(root),out):
        raise ValueError('native parent hash failed')
    raw=out.raw
    return [raw[i:i+32] for i in range(0,len(raw),32)]


def chunk_value(data,index,key):
    key_check(key)
    if len(data)!=1024 or not 0<=index<65536:raise ValueError('invalid chunk/index')
    out=C.create_string_buffer(32)
    if library().ph_chunk_value(data,index,key,out):raise ValueError('native chunk hash failed')
    return out.raw
