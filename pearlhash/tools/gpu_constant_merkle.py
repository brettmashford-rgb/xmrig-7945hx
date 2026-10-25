"""GPU constant-matrix CV tree and sparse openings; <=384 MiB working CVs. ISC.

No complete matrix, mining, proof submission, clock or service operations.
Returned openings are independently checked with the existing CPU primitives.
"""
import ctypes as C
import time
from reference.native_hash import key_check,chunk_value,small_hash
from reference.plain_proof import Opening
from tools.check_mma_gpu import MmaDevice

GUARD=b'\xa5'*16


def validate(key,fill,total,rows,width,tail):
    key_check(key)
    if (type(fill)is not int or not 0<=fill<=255 or type(total)is not int or not 1<=total<=8388608
            or type(width)is not int or width<=0 or width%1024 or type(tail)is not bytes or len(tail)not in(0,16)
            or type(rows)is not list or not rows or any(type(r)is not int or r<0 for r in rows)
            or rows!=sorted(set(rows)) or (rows[-1]+1)*width>total*1024):
        raise ValueError('invalid bounded GPU constant opening')
    selected=tuple(i for row in rows for i in range(row*width//1024,(row+1)*width//1024))
    if len(selected)>4096:raise ValueError('selected leaf cap exceeded')
    return selected


class ConstantMerkleGpu(MmaDevice):
    def write(self,pointer,raw):
        buffer=C.create_string_buffer(raw,len(raw))
        self.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],pointer,buffer,len(raw))

    def guarded_cv(self,count):
        size=count*32;raw=C.c_ulonglong()
        self.api('cuMemAlloc_v2',[C.POINTER(C.c_ulonglong),C.c_size_t],C.byref(raw),size+32)
        self.allocations.append(raw)
        self.write(raw,GUARD);self.write(C.c_ulonglong(raw.value+size+16),GUARD)
        return raw,C.c_ulonglong(raw.value+16),size

    def read(self,pointer,offset,size):
        value=C.create_string_buffer(size)
        self.api('cuMemcpyDtoH_v2',[C.c_void_p,C.c_ulonglong,C.c_size_t],
                 value,C.c_ulonglong(pointer.value+offset),size)
        return value.raw

    def check(self,buffer):
        raw,pointer,size=buffer
        if self.read(raw,0,16)!=GUARD or self.read(raw,size+16,16)!=GUARD:
            raise RuntimeError('constant Merkle CV guard changed')

    def opening(self,key,fill,total,rows,width,*,tail=b'',current=lambda:None):
        selected=validate(key,fill,total,rows,width,tail)
        current();mark=len(self.allocations);started=time.monotonic()
        try:
            key_ptr=self.allocate(key);tail_ptr=self.allocate(tail or bytes(16))
            buffers=[self.guarded_cv(total)]
            if total>1:buffers.append(self.guarded_cv((total+1)//2))
            self.launch(b'constant_merkle_leaves',(key_ptr,C.c_uint(fill),C.c_uint(total),tail_ptr,
                        C.c_uint(len(tail)),buffers[0][1]),(total+127)//128,128)
            self.api('cuCtxSynchronize',[]);self.check(buffers[0]);current()
            leaf_seconds=time.monotonic()-started
            block=bytes([fill])*1024
            def leaf(index):return block[:-16]+tail if tail and index+1==total else block
            for index in sorted({0,total//2,total-1}):
                expected=small_hash(leaf(index),key)if total==1 else chunk_value(leaf(index),index,key)
                if self.read(buffers[0][1],index*32,32)!=expected:
                    raise RuntimeError('constant GPU leaf differs from independent CPU')
            siblings=[];active=set(selected);length=total;level=0
            fold_started=time.monotonic()
            while length>1:
                current();source=buffers[level%2];destination=buffers[(level+1)%2]
                for index in sorted(active):
                    sibling=index^1
                    if sibling<length and sibling not in active:
                        siblings.append(self.read(source[1],sibling*32,32))
                self.launch(b'constant_merkle_parents',(source[1],key_ptr,C.c_uint(length),destination[1]),
                            (((length+1)//2)+127)//128,128)
                self.api('cuCtxSynchronize',[])
                self.check(source);self.check(destination)
                length=(length+1)//2;level+=1;active={i//2 for i in active}
            root=self.read(buffers[level%2][1],0,32)
            value=Opening([leaf(i)for i in selected],list(selected),total,root,siblings,rows[:])
            value.verify(key);current()
            self.last_timing={'leaf_and_setup_seconds':leaf_seconds,
                'parent_and_opening_seconds':time.monotonic()-fold_started,
                'total_seconds':time.monotonic()-started,'working_cv_bytes':sum(b[2]+32 for b in buffers)}
            return value
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)
