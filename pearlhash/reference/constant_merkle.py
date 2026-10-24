"""Bounded streaming constant-matrix openings; no complete matrix allocation. ISC."""
import ctypes as C
from reference.native_hash import library,key_check
from reference.plain_proof import Opening


def constant_opening(key,fill,total_chunks,rows,width,*,tail=b''):
    key_check(key)
    if (type(fill) is not int or not 0<=fill<=255 or type(total_chunks) is not int
        or not 1<=total_chunks<=8388608 or type(width) is not int or width<=0
        or type(tail) is not bytes or len(tail) not in (0,16)
        or not isinstance(rows,list) or not rows or any(type(r) is not int or r<0 for r in rows)
        or rows!=sorted(set(rows)) or (rows[-1]+1)*width>total_chunks*1024):
        raise ValueError('invalid constant matrix opening request')
    selected=sorted({i for row in rows for i in range(row*width//1024,((row+1)*width-1)//1024+1)})
    if len(selected)>4096:raise ValueError('selected leaf limit exceeds 4096')
    ix=(C.c_uint64*len(selected))(*selected);capacity=65536
    siblings=C.create_string_buffer(capacity*32);count=C.c_size_t();root=C.create_string_buffer(32)
    function=library().ph_constant_merkle
    function.argtypes=[C.c_void_p,C.c_ubyte,C.c_uint64,C.c_void_p,C.c_size_t,
                       C.POINTER(C.c_uint64),C.c_size_t,C.c_void_p,C.c_size_t,
                       C.POINTER(C.c_size_t),C.c_void_p]
    function.restype=C.c_int
    if function(key,fill,total_chunks,tail,len(tail),ix,len(selected),siblings,capacity,C.byref(count),root):
        raise ValueError('native streaming Merkle construction failed')
    block=bytes([fill])*1024
    leaves=[block[:-len(tail)]+tail if tail and i+1==total_chunks else block for i in selected]
    raw=siblings.raw[:count.value*32]
    value=Opening(leaves,selected,total_chunks,root.raw,[raw[i:i+32]for i in range(0,len(raw),32)],rows[:])
    value.verify(key)
    return value
