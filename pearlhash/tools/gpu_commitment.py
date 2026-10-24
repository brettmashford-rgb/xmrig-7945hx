"""Bounded GPU commitment leaves with independent CPU tree comparison. ISC.

Only leaf chunk CVs run on the GPU; parent folds and Merkle openings use CPU.
No pool connection, mining scheduler, service or clock operations.
"""
import ctypes as C
from reference.native_hash import key_check
from reference.plain_proof import Tree
from tools.cuda_driver import CudaDevice


def validate_inputs(first,key,data):
    key_check(key)
    if type(data) is not bytes or len(data)%1024 or len(data)>4096*1024:
        raise ValueError('expected 0..4096 complete byte chunks')
    count=len(data)//1024
    if type(first) is not int or not 0<=first<=0xffffffffffffffff or (count and first+count-1>0xffffffffffffffff):
        raise ValueError('chunk counter range exceeds u64')
    return count


class GpuCommitments(CudaDevice):
    def compute(self,first,key,data):
        count=validate_inputs(first,key,data)
        mark=len(self.allocations)
        try:
            key_ptr=self.allocate(key)
            source=self.allocate(data or bytes(4))
            destination=self.allocate(b'\xa5'*(count*32+32))
            interior=C.c_ulonglong(destination.value+16)
            first_arg=C.c_ulonglong(first);count_arg=C.c_uint(count)
            function=C.c_void_p()
            self.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                     C.byref(function),self.module,b'keyed_chunk_cvs')
            args=(C.c_void_p*5)(*(C.cast(C.byref(v),C.c_void_p)
                                 for v in (source,key_ptr,first_arg,count_arg,interior)))
            self.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                     function,max(1,(count+127)//128),1,1,128,1,1,0,None,args,None)
            self.api('cuCtxSynchronize',[])
            result=C.create_string_buffer(count*32+32)
            self.api('cuMemcpyDtoH_v2',[C.c_void_p,C.c_ulonglong,C.c_size_t],
                     result,destination,len(result))
            if result.raw[:16]!=b'\xa5'*16 or result.raw[-16:]!=b'\xa5'*16:
                raise RuntimeError('chunk kernel output guard changed')
            return result.raw[16:-16]
        finally:
            for pointer in reversed(self.allocations[mark:]):
                self.release(pointer)

    def chunk_cvs(self,data,key,*,batch_chunks=128):
        key_check(key)
        if (type(data) is not bytes or not data or len(data)%1024
            or len(data)>64*1024*1024 or type(batch_chunks) is not int
            or not 1<=batch_chunks<=4096):
            raise ValueError('invalid bounded commitment input or batch size')
        result=[]
        for start in range(0,len(data),batch_chunks*1024):
            batch=data[start:start+batch_chunks*1024]
            raw=self.compute(start//1024,key,batch)
            if type(raw) is not bytes or len(raw)!=len(batch)//1024*32:
                raise ValueError('GPU backend returned invalid CV output length')
            result.extend(raw[i:i+32]for i in range(0,len(raw),32))
        return result


def checked_tree(data,key,leaf_hasher):
    actual=Tree(data,key,leaf_hasher=leaf_hasher)
    expected=Tree(data,key)
    if actual.layers!=expected.layers:
        raise ValueError('GPU commitment tree differs from independent CPU tree')
    return actual
