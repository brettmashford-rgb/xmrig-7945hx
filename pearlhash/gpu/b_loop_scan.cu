// ISC. Quad5 loop grouping and grouped early operand preparation experiments.
#include "b_quad_scan.cu"

struct LoopOperands {unsigned a0,a1,a2,a3,b0,b1,c0,c1;};
__device__ __forceinline__ LoopOperands loop_operands(const unsigned *cache,const unsigned *pb,
        const signed char *ua,const unsigned *ra,unsigned offset,unsigned lane) {
    LoopOperands value;
    b_quad_fragments<5>(cache,pb,offset,lane,value.b0,value.b1,value.c0,value.c1);
    unsigned group=lane/4,thread=lane%4;
    value.a0=cached_a_word(ua,ra[group],offset+thread*4,true);
    value.a1=cached_a_word(ua,group<2?ra[group+8]:0,offset+thread*4,group<2);
    value.a2=cached_a_word(ua,ra[group],offset+thread*4+16,true);
    value.a3=cached_a_word(ua,group<2?ra[group+8]:0,offset+thread*4+16,group<2);
    return value;
}

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first
#define PH_BQ_VALUES ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first

template<bool EARLY>
__device__ __forceinline__ void b_loop_scan_body(PH_BQ_ARGS) {
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
    // Each outer step ends at exactly the original 128-K transcript boundary.
    for(unsigned base=0;base<32768;base+=128) {
        if(EARLY) {
            LoopOperands current=loop_operands(cache,pb,ua,ra,base,lane);
            #pragma unroll
            for(unsigned step=0;step<4;++step) {
                LoopOperands next;
                // Final step has no lookahead: never load beyond this 128-K group.
                if(step<3)next=loop_operands(cache,pb,ua,ra,base+(step+1)*32,lane);
                mma_accumulate(current.a0,current.a1,current.a2,current.a3,current.b0,current.b1,d0,d1,d2,d3);
                mma_accumulate(current.a0,current.a1,current.a2,current.a3,current.c0,current.c1,e0,e1,e2,e3);
                if(step<3)current=next;
            }
        } else {
            #pragma unroll
            for(unsigned step=0;step<4;++step) {
                LoopOperands current=loop_operands(cache,pb,ua,ra,base+step*32,lane);
                mma_accumulate(current.a0,current.a1,current.a2,current.a3,current.b0,current.b1,d0,d1,d2,d3);
                mma_accumulate(current.a0,current.a1,current.a2,current.a3,current.c0,current.c1,e0,e1,e2,e3);
            }
        }
        unsigned folded=unsigned(d0)^unsigned(d1)^unsigned(e0)^unsigned(e1);
        if(group<2)folded^=unsigned(d2)^unsigned(d3)^unsigned(e2)^unsigned(e3);
        for(unsigned delta=16;delta;delta>>=1)folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
        unsigned slot=(base/128)%16;
        if(lane==slot)word=((word<<13)|(word>>19))^folded;
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

extern "C" __global__ void b_quad_grouped_scan(PH_BQ_ARGS) {b_loop_scan_body<false>(PH_BQ_VALUES);}
extern "C" __global__ void b_quad_early_scan(PH_BQ_ARGS) {b_loop_scan_body<true>(PH_BQ_VALUES);}
#undef PH_BQ_VALUES
#undef PH_BQ_ARGS
