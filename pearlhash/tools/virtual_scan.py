"""Virtual constant-signal fragments over full GPU noise tables. ISC.

Correctness backend only: supplied seeds, <=64-MiB table payload, CPU references
for every tested tile. No pool IO, complete production search or benchmark.
"""
import ctypes as C
from pathlib import Path
import struct
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.tile_ranges import RangeBatch
from tools.check_range_scan_gpu import ConstantProfile,RangeBackend
from tools.check_noise_mma_gpu import reference_tables
from tools.check_tile_scan_gpu import MAX_BOUND,TileQuery,TileScanner,decode_candidates,query_reference,validate_scan

TABLE_CAP=64*1024*1024


def table_payload(profile):
    if not isinstance(profile,ConstantProfile):raise ValueError('expected validated constant profile')
    profile.__post_init__()
    size=(profile.m+profile.n)*profile.rank+8*profile.k+16
    if size>TABLE_CAP:raise ValueError('virtual table payload exceeds 64-MiB cap')
    return size


def pack_global_queries(profile,queries):
    table_payload(profile)
    if not 1<=len(queries)<=64:raise ValueError('expected 1..64 virtual tile queries')
    words=[]
    for query in queries:
        for slots,limit in ((query.rows,profile.m),(query.cols,profile.n)):
            if not 1<=len(slots)<=32 or any(type(i)is not int or not 0<=i<limit for i in slots):
                raise ValueError('invalid global virtual tile indices')
        words.extend((len(query.rows),len(query.cols)))
        words.extend((*query.rows,*([0]*(32-len(query.rows)))))
        words.extend((*query.cols,*([0]*(32-len(query.cols)))))
    return struct.pack(f'<{len(words)}I',*words)


def global_reference(profile,queries):
    pack_global_queries(profile,queries);result=[]
    for query in queries:
        maps=((tuple(range(len(query.rows))),tuple(range(len(query.cols)))),)
        batch=RangeBatch(0,1,query.rows,query.cols,maps)
        matrix=profile.case(batch).matrix()
        result.extend(query_reference(matrix,[TileQuery(*maps[0])]))
    return result


class VirtualTables:
    """Own only this cache's allocations; queries never upload signal matrices."""
    def __init__(self,device,profile):
        self.device=device;self.profile=profile;self.payload=table_payload(profile)
        self.owned=[];self.closed=False;self.checked={'A':set(),'B':set()}
        self.buffers={}
        try:
            self.key_a=self.allocate(profile.seed_a);self.key_b=self.allocate(profile.seed_b)
            self.tail=self.allocate(profile.tail)
            for side,rows,key,label in (('A',profile.m,self.key_a,b'A_tensor'),('B',profile.n,self.key_b,b'B_tensor')):
                raw,u=self.guarded(rows*profile.rank);praw,p=self.guarded(profile.k*4)
                self.buffers[side]=(raw,u,praw,p,rows)
                blocks=rows*profile.rank//32;domain=C.c_uint(int.from_bytes(label[:4],'little'))
                device.launch(b'noise_uniform_range',(key,u,C.c_uint(0),C.c_uint(blocks),domain),(blocks+127)//128,128)
                device.launch(b'noise_permutation',(key,p,C.c_uint(profile.k),C.c_uint(profile.rank),domain),(profile.k//8+127)//128,128)
            device.api('cuCtxSynchronize',[]);self.check_guards()
        except BaseException:
            self.close();raise

    def allocate(self,data):
        pointer=self.device.allocate(data);self.owned.append(pointer);return pointer

    def guarded(self,size):
        raw=self.allocate(b'\xa5'*(size+32));return raw,C.c_ulonglong(raw.value+16)

    def read(self,pointer,offset,size):
        result=C.create_string_buffer(size)
        self.device.api('cuMemcpyDtoH_v2',[C.c_void_p,C.c_ulonglong,C.c_size_t],
                        result,C.c_ulonglong(pointer.value+offset),size)
        return result.raw

    def check_guards(self):
        if self.closed:raise ValueError('virtual cache is closed')
        for raw,u,praw,p,rows in self.buffers.values():
            for pointer,size in ((raw,rows*self.profile.rank),(praw,self.profile.k*4)):
                if self.read(pointer,0,16)!=b'\xa5'*16 or self.read(pointer,size+16,16)!=b'\xa5'*16:
                    raise RuntimeError('virtual noise-table output guard changed')

    def check_rows(self,side,indices):
        if self.closed:raise ValueError('virtual cache is closed')
        raw,u,praw,p,limit=self.buffers[side]
        if any(type(i)is not int or not 0<=i<limit for i in indices):raise ValueError('invalid uniform check row')
        rows=sorted(set(indices)-self.checked[side])
        if not rows:return
        label=b'A_tensor'if side=='A'else b'B_tensor'
        seed=self.profile.seed_a if side=='A'else self.profile.seed_b
        uniform,pairs=reference_tables(rows,self.profile.k,self.profile.rank,label,seed)
        actual=b''.join(self.read(u,row*self.profile.rank,self.profile.rank)for row in rows)
        if actual!=uniform or self.read(p,0,len(pairs))!=pairs:
            raise RuntimeError('virtual uniform/permutation table differs from independent CPU calculation')
        self.checked[side].update(rows);self.check_guards()

    def inputs(self):
        if self.closed:raise ValueError('virtual cache is closed')
        return self.buffers['A'][1],self.buffers['B'][1],self.buffers['A'][3],self.buffers['B'][3],self.tail

    def close(self):
        if not self.closed:
            for pointer in reversed(self.owned):self.device.release(pointer)
            self.owned.clear();self.closed=True


class VirtualScanner(TileScanner):
    def scan_virtual(self,tables,queries,reference,bounds,capacity,generation,*,audit=False):
        if tables.device is not self or tables.closed:raise ValueError('foreign or closed virtual cache')
        profile=tables.profile;descriptors=pack_global_queries(profile,queries)
        validate_scan(bounds,capacity,generation)
        if len(bounds)!=len(queries)or len(reference)!=len(queries):raise ValueError('virtual query count differs')
        tables.check_rows('A',[r for q in queries for r in q.rows])
        tables.check_rows('B',[c for q in queries for c in q.cols])
        mark=len(self.allocations)
        try:
            desc=self.allocate(descriptors);limits=self.allocate(b''.join(v.to_bytes(32,'little')for v in bounds))
            status,s=self.guarded(8);zero=C.create_string_buffer(bytes(8),8)
            self.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],s,zero,8)
            queue,q=self.guarded(capacity*44);trace,t=self.guarded(len(queries)*64 if audit else 0)
            arguments=(*tables.inputs(),desc,limits,tables.key_a,s,q,t,C.c_uint(audit),C.c_uint(capacity),
                       C.c_uint(len(queries)),C.c_uint(profile.m),C.c_uint(profile.n),C.c_uint(profile.k),
                       C.c_uint(profile.rank),C.c_int(profile.fill),C.c_ulonglong(generation))
            self.launch(b'virtual_tile_scan',arguments,len(queries),256);self.api('cuCtxSynchronize',[])
            result=decode_candidates(self.checked_download(queue,capacity*44),self.checked_download(status,8),
                                     bounds,capacity,generation,reference)
            words=self.checked_download(trace,len(queries)*64 if audit else 0)
            if audit and words!=b''.join(item[0]for item in reference):raise RuntimeError('virtual transcript differs')
            tables.check_guards();return result
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)

    def probe(self,tables):
        profile=tables.profile
        ra=tuple(range(profile.m))if profile.m<=32 else tuple(sorted({0,profile.m//2,profile.m-1}))
        cb=tuple(range(profile.n))if profile.n<=32 else tuple(sorted({0,profile.n//2,profile.n-1}))
        batch=RangeBatch(0,1,ra,cb,((tuple(range(len(ra))),tuple(range(len(cb)))),))
        matrix=profile.case(batch).matrix();requests=[]
        tables.check_rows('A',ra);tables.check_rows('B',cb)
        for side,rows in ((0,ra),(1,cb)):
            for row in rows:
                for offset in range(0,profile.k,4):requests.extend((side,row,offset))
        expected=bytes(v&255 for v in matrix.a+matrix.bt);count=len(requests)//3
        mark=len(self.allocations)
        try:
            source=self.allocate(struct.pack(f'<{len(requests)}I',*requests));output,o=self.guarded(len(expected))
            arguments=(*tables.inputs(),source,o,C.c_uint(count),C.c_uint(profile.m),C.c_uint(profile.n),
                       C.c_uint(profile.k),C.c_uint(profile.rank),C.c_int(profile.fill))
            self.launch(b'virtual_probe',arguments,(count+127)//128,128);self.api('cuCtxSynchronize',[])
            if self.checked_download(output,len(expected))!=expected:raise RuntimeError('virtual signed-byte probes differ')
            tables.check_guards();return len(expected)
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)


class VirtualRangeBackend:
    """Same reference/queue gate as the prior backend, with virtual GPU inputs."""
    def __init__(self,profile,device=None,*,bound=MAX_BOUND):
        table_payload(profile)
        if type(bound)is not int or not 0<=bound<=MAX_BOUND:raise ValueError('invalid virtual bound')
        self.profile=profile;self.device=device;self.bound=bound;self.batch=None
        self.cpu=RangeBackend(profile,None,bound=bound)if device is None else None
        self.tables=VirtualTables(device,profile)if device else None

    def __call__(self,batch,capacity,generation):
        if self.cpu:return self.cpu(batch,capacity,generation)
        if batch!=self.batch:
            matrix=self.profile.case(batch).matrix();local=[TileQuery(*mapping)for mapping in batch.maps]
            self.reference=query_reference(matrix,local)
            self.queries=[TileQuery(tuple(batch.rows[r]for r in q.rows),tuple(batch.cols[c]for c in q.cols))for q in local]
            self.batch=batch
        return self.device.scan_virtual(self.tables,self.queries,self.reference,[self.bound]*len(self.queries),
                                        capacity,generation,audit=True)

    def close(self):
        if self.tables:self.tables.close()
        if self.cpu:self.cpu.close()
        self.batch=None
