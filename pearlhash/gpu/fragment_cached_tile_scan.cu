// ISC. Coalesced immutable K-major fragments, same query math and queue ABI.
#include "cached_tile_scan.cu"
#include "fragment_layout.h"

extern "C" __global__ void materialize_fragment_rows(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,const unsigned *indices,
    unsigned *output,unsigned rows,unsigned side,unsigned m,unsigned n,unsigned k,
    unsigned rank,int fill) {
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(!inputs.valid()||!rows||k!=32768||rank!=128||fill!=64||side>1)return;
    unsigned word=blockIdx.x*blockDim.x+threadIdx.x;
    if(word>=rows*(k/4))return;
    unsigned block16=word/(rows*4),within=word%(rows*4);
    unsigned row=within/4,offset=block16*16+(within%4)*4;
    output[word]=inputs.pack(side,indices,row,rows,offset);
}

__device__ __forceinline__ unsigned fragment_cached_pack(const signed char *input,unsigned rows,
    unsigned row,unsigned offset,bool live) {
    return live?reinterpret_cast<const unsigned *>(input)[fragment_word_index(rows,row,offset)]:0U;
}

extern "C" __global__ void fragment_cached_tile_scan(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k,
    unsigned rank,int fill,unsigned long long generation) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32,query=blockIdx.x*8+warp;
    if(blockDim.x!=256||query>=query_count||!m||!n||k!=32768||rank!=128||fill!=64)return;
    const unsigned *desc=descriptors+query*66;
    if(desc[0]!=10||desc[1]!=16)return;
    const unsigned *ra=desc+2,*cb=desc+34;
    bool invalid=lane<10?ra[lane]>=m:(lane<26?cb[lane-10]>=n:false);
    if(__any_sync(0xffffffffU,invalid))return;
    unsigned group=lane/4,thread=lane%4;
    int d0=0,d1=0,d2=0,d3=0,e0=0,e1=0,e2=0,e3=0;
    unsigned word=0;
    for(unsigned offset=0;offset<32768;offset+=32) {
        unsigned a0=fragment_cached_pack(ua,m,ra[group],offset+thread*4,true);
        unsigned a1=fragment_cached_pack(ua,m,group<2?ra[group+8]:0,offset+thread*4,group<2);
        unsigned a2=fragment_cached_pack(ua,m,ra[group],offset+thread*4+16,true);
        unsigned a3=fragment_cached_pack(ua,m,group<2?ra[group+8]:0,offset+thread*4+16,group<2);
        unsigned b0=fragment_cached_pack(ub,n,cb[group],offset+thread*4,true);
        unsigned b1=fragment_cached_pack(ub,n,cb[group],offset+thread*4+16,true);
        unsigned c0=fragment_cached_pack(ub,n,cb[group+8],offset+thread*4,true);
        unsigned c1=fragment_cached_pack(ub,n,cb[group+8],offset+thread*4+16,true);
        mma_accumulate(a0,a1,a2,a3,b0,b1,d0,d1,d2,d3);
        mma_accumulate(a0,a1,a2,a3,c0,c1,e0,e1,e2,e3);
        if((offset+32)%128==0) {
            unsigned folded=unsigned(d0)^unsigned(d1)^unsigned(e0)^unsigned(e1);
            if(group<2)folded^=unsigned(d2)^unsigned(d3)^unsigned(e2)^unsigned(e3);
            for(unsigned delta=16;delta;delta>>=1)folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
            unsigned slot=((offset+32)/128-1)%16;
            if(lane==slot)word=((word<<13)|(word>>19))^folded;
        }
    }
    unsigned words[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word,i);
    if(lane)return;
    unsigned digest[8];ph::keyed64(words,key,digest);
    if(audit)for(unsigned i=0;i<16;++i)audit_words[query*16+i]=words[i];
    if(!ph::digest_meets_bound(digest,bounds+query*8))return;
    unsigned slot=atomicAdd(status,1U);
    if(slot>=capacity){atomicExch(status+1,1U);return;}
    unsigned *out=candidates+slot*11;
    out[0]=query;out[1]=unsigned(generation);out[2]=unsigned(generation>>32);
    for(unsigned i=0;i<8;++i)out[3+i]=digest[i];
}
