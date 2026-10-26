// ISC. Early A/B operands alone; original 32-K loop, no grouped/unrolled iterations.
#include "b_loop_scan.cu"

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first
#define PH_BQ_VALUES ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first

extern "C" __global__ void b_quad_early_only_scan(PH_BQ_ARGS) {
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
    __shared__ unsigned uniform_cache[8][5*128];
    unsigned *cache=uniform_cache[warp];
    for(unsigned i=lane;i<16*128;i+=32) {
        unsigned row=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*5*4+row]=
            static_cast<unsigned char>(ub[cb[row]*128+index]);
    }
    __syncwarp(0xffffffffU);
    unsigned group=lane/4;
    int d0=0,d1=0,d2=0,d3=0,e0=0,e1=0,e2=0,e3=0;
    unsigned word=0;
    // Original 32-K loop and transcript cadence; carry one future operand set.
    LoopOperands current=loop_operands(cache,pb,ua,ra,0,lane);
    #pragma unroll 1
    for(unsigned offset=0;offset<32768;offset+=32) {
        LoopOperands next;
        // Never prepare offset 32768: the final operand set starts at 32736.
        if(offset+32<32768)next=loop_operands(cache,pb,ua,ra,offset+32,lane);
        mma_accumulate(current.a0,current.a1,current.a2,current.a3,current.b0,current.b1,d0,d1,d2,d3);
        mma_accumulate(current.a0,current.a1,current.a2,current.a3,current.c0,current.c1,e0,e1,e2,e3);
        if((offset+32)%128==0) {
            unsigned folded=unsigned(d0)^unsigned(d1)^unsigned(e0)^unsigned(e1);
            if(group<2)folded^=unsigned(d2)^unsigned(d3)^unsigned(e2)^unsigned(e3);
            for(unsigned delta=16;delta;delta>>=1)folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
            unsigned slot=((offset+32)/128-1)%16;
            if(lane==slot)word=((word<<13)|(word>>19))^folded;
        }
        if(offset+32<32768)current=next;
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

#undef PH_BQ_VALUES
#undef PH_BQ_ARGS
