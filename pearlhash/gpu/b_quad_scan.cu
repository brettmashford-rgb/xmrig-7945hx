// ISC. Four-row packed B reconstruction; established A/MMA/transcript/hash unchanged.
#include "snapshot_scan.cu"
#include "b_quad.h"

template<unsigned STRIDE>
__device__ __forceinline__ void b_quad_fragments(const unsigned *cache,const unsigned *pairs,
    unsigned offset,unsigned lane,unsigned &b0,unsigned &b1,unsigned &c0,unsigned &c1) {
    unsigned index=offset+(lane&15),block=lane>>4;
    unsigned p0=pairs[index],p1=pairs[index+16];
    unsigned low0=b_quad_value(cache,STRIDE,p0,block),low1=b_quad_value(cache,STRIDE,p1,block);
    unsigned high0=b_quad_value(cache,STRIDE,p0,block+2),high1=b_quad_value(cache,STRIDE,p1,block+2);
    unsigned group=lane/4,thread=lane%4;b0=b1=c0=c1=0;
    #pragma unroll
    for(unsigned byte=0;byte<4;++byte) {
        unsigned source=b_quad_source(group,thread,byte);
        b0|=b_quad_pick(__shfl_sync(0xffffffffU,low0,source),group,byte);
        b1|=b_quad_pick(__shfl_sync(0xffffffffU,low1,source),group,byte);
        c0|=b_quad_pick(__shfl_sync(0xffffffffU,high0,source),group,byte);
        c1|=b_quad_pick(__shfl_sync(0xffffffffU,high1,source),group,byte);
    }
}

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first
#define PH_BQ_VALUES ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first

template<unsigned STRIDE>
__device__ __forceinline__ void b_quad_scan_body(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32,query=blockIdx.x*8+warp;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||query>=query_count||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||row_count>512||!column_count||column_count>16384
            ||first>=row_count*column_count||query_count>row_count*column_count-first)return;
    ResidentAxisOffsets axes=resident_axis_offsets(first,query,column_count);
    const unsigned *ra=row_axes+axes.row*32,*cb=column_axes+axes.col*32;
    bool invalid=lane<10?ra[lane]>=m:(lane<26?cb[lane-10]>=n:false);
    if(__any_sync(0xffffffffU,invalid))return;
    // Original coalesced global-byte reads; regroup rows into four-byte words.
    __shared__ unsigned uniform_cache[8][STRIDE*128];
    unsigned *cache=uniform_cache[warp];
    for(unsigned i=lane;i<16*128;i+=32) {
        unsigned row=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*STRIDE*4+row]=
            static_cast<unsigned char>(ub[cb[row]*128+index]);
    }
    __syncwarp(0xffffffffU);
    unsigned group=lane/4,thread=lane%4;
    int d0=0,d1=0,d2=0,d3=0,e0=0,e1=0,e2=0,e3=0;
    unsigned word=0;
    for(unsigned offset=0;offset<32768;offset+=32) {
        unsigned b0,b1,c0,c1;
        b_quad_fragments<STRIDE>(cache,pb,offset,lane,b0,b1,c0,c1);
        unsigned a0=cached_a_word(ua,ra[group],offset+thread*4,true);
        unsigned a1=cached_a_word(ua,group<2?ra[group+8]:0,offset+thread*4,group<2);
        unsigned a2=cached_a_word(ua,ra[group],offset+thread*4+16,true);
        unsigned a3=cached_a_word(ua,group<2?ra[group+8]:0,offset+thread*4+16,group<2);
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

extern "C" __global__ void b_quad_packed_scan(PH_BQ_ARGS) {b_quad_scan_body<4>(PH_BQ_VALUES);}
extern "C" __global__ void b_quad_padded_scan(PH_BQ_ARGS) {b_quad_scan_body<5>(PH_BQ_VALUES);}
#undef PH_BQ_VALUES
#undef PH_BQ_ARGS
