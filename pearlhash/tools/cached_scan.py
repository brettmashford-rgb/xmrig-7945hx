"""Bounded materialized row cache reused by many production tiles. ISC.

Does not change nonce inputs, targets, transcript math or pool protocol. The
cache is explicit and immutable, capped at 128 MiB; it never allocates full B.
"""
import ctypes as C
from dataclasses import replace
import struct

from tools.production_scan import ProductionCandidateScanner,require_production
from tools.wide_scan import pack_wide,validate_wide,decode_wide
from tools.virtual_scan import pack_global_queries,global_reference
from tools.check_tile_scan_gpu import TileQuery
from tools.candidate_scan import verify_returned

CACHE_CAP=128*1024*1024


def row_plan(profile,queries):
    require_production(profile,queries)
    if not 1<=len(queries)<=4096:raise ValueError('expected 1..4096 cached queries')
    for first in range(0,len(queries),64):pack_global_queries(profile,queries[first:first+64])
    a=tuple(sorted({r for q in queries for r in q.rows}))
    b=tuple(sorted({c for q in queries for c in q.cols}))
    size=(len(a)+len(b))*profile.k
    if size>CACHE_CAP:raise ValueError('materialized row cache exceeds 128 MiB')
    return a,b,size


class RowCache:
    def __init__(self,tables,queries):
        if tables.closed:raise ValueError('closed noise cache')
        self.tables=tables;self.device=tables.device;self.closed=False;self.owned=[];self.buffers=[]
        self.rows_a,self.rows_b,self.bytes=row_plan(tables.profile,queries)
        self.maps=({r:i for i,r in enumerate(self.rows_a)},{c:i for i,c in enumerate(self.rows_b)})
        self.local_profile=replace(tables.profile,m=len(self.rows_a),n=len(self.rows_b))
        try:
            for side,rows in enumerate((self.rows_a,self.rows_b)):
                indices=self.allocate(struct.pack(f'<{len(rows)}I',*rows))
                raw,out=self.device.guarded(len(rows)*32768);self.owned.append(raw)
                self.buffers.append((raw,out,len(rows)*32768))
                arguments=(*tables.inputs(),indices,out,C.c_uint(len(rows)),C.c_uint(side),
                    C.c_uint(tables.profile.m),C.c_uint(tables.profile.n),C.c_uint(32768),C.c_uint(128),C.c_int(64))
                words=len(rows)*(32768//4)
                self.device.launch(b'materialize_selected_rows',arguments,(words+127)//128,128)
            self.device.api('cuCtxSynchronize',[]);self.check_guards()
        except BaseException:self.close();raise

    def allocate(self,raw):
        pointer=self.device.allocate(raw);self.owned.append(pointer);return pointer

    def remap(self,queries):
        if self.closed:raise ValueError('closed materialized row cache')
        require_production(self.tables.profile,queries)
        for first in range(0,len(queries),64):pack_global_queries(self.tables.profile,queries[first:first+64])
        try:return tuple(TileQuery(tuple(self.maps[0][r]for r in q.rows),
                                   tuple(self.maps[1][c]for c in q.cols))for q in queries)
        except KeyError:raise ValueError('query row absent from immutable cache')from None

    def check_guards(self):
        if self.closed:raise ValueError('closed materialized row cache')
        self.tables.check_guards()
        for raw,out,size in self.buffers:
            if self.tables.read(raw,0,16)!=b'\xa5'*16 or self.tables.read(raw,size+16,16)!=b'\xa5'*16:
                raise RuntimeError('materialized row cache guard changed')

    def close(self):
        if not self.closed:
            self.device.api('cuCtxSynchronize',[])
            for pointer in reversed(self.owned):self.device.release(pointer)
            self.owned.clear();self.closed=True


class CachedCandidateScanner(ProductionCandidateScanner):
    def scan_cached(self,cache,queries,bounds,capacity,generation,*,audit=False):
        if cache.closed or cache.device is not self or cache.tables.closed:raise ValueError('foreign or closed row cache')
        validate_wide(bounds,capacity,generation)
        if len(queries)!=len(bounds):raise ValueError('cached query/target count differs')
        descriptors=pack_wide(cache.local_profile,cache.remap(queries))
        mark=len(self.allocations)
        try:
            desc=self.allocate(descriptors);limits=self.allocate(b''.join(b.to_bytes(32,'little')for b in bounds))
            status,s=self.guarded(8);zero=C.create_string_buffer(bytes(8),8)
            self.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],s,zero,8)
            queue,q=self.guarded(capacity*44);trace_bytes=len(queries)*64 if audit else 0
            trace,t=self.guarded(trace_bytes);null=C.c_ulonglong(0)
            args=(cache.buffers[0][1],cache.buffers[1][1],null,null,null,desc,limits,cache.tables.key_a,
                  s,q,t,C.c_uint(audit),C.c_uint(capacity),C.c_uint(len(queries)),
                  C.c_uint(len(cache.rows_a)),C.c_uint(len(cache.rows_b)),C.c_uint(32768),
                  C.c_uint(128),C.c_int(64),C.c_ulonglong(generation))
            self.launch(b'cached_tile_scan',args,(len(queries)+7)//8,256)
            self.dispatches+=1;self.wide_dispatches+=1;self.api('cuCtxSynchronize',[])
            result=decode_wide(self.checked_download(queue,capacity*44),self.checked_download(status,8),bounds,capacity,generation)
            raw=self.checked_download(trace,trace_bytes)
            self.last_transcripts=tuple(struct.unpack_from('<16I',raw,i*64)for i in range(len(queries)))if audit else None
            cache.check_guards();references={}
            def reference(query):
                if query not in references:
                    references[query]=global_reference(cache.tables.profile,(query,))[0][1];self.unique_cpu_checks+=1
                return references[query]
            self.verified_tiles+=verify_returned(result,queries,reference)
            return result
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)
