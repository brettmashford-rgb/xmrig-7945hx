// ISC. v072: v070 eight-step B sharing plus v071 partitioned transcript folds.
#include "cta_b_scan.cu"
#include "partition_fold.h"
#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first


extern "C" __global__ void partition_pointer_scan(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&3U)||row_count>512||!column_count||column_count>16384
            ||first>=row_count*column_count||query_count>row_count*column_count-first)return;
    unsigned ordinal=(first&~3U)+(blockIdx.x*8+warp)*4U;
    if(ordinal>=first+query_count)return;
    unsigned base=four_tile_row(ordinal,column_count),col=four_tile_column(ordinal,column_count);
    const unsigned *cb=column_axes+col*32U;
    bool invalid=lane<16?cb[lane]>=n:false;
    #pragma unroll
    for(unsigned t=0;t<4;++t)if(lane<10)invalid|=row_axes[(base+t)*32U+lane]>=m;
    if(__any_sync(0xffffffffU,invalid))return;
    bool active0=ordinal>=first,active1=ordinal+1>=first&&ordinal+1<first+query_count;
    bool active2=ordinal+2>=first&&ordinal+2<first+query_count,active3=ordinal+3<first+query_count;
    __shared__ unsigned uniform_cache[8][6*128];
    unsigned *cache=uniform_cache[warp];
    for(unsigned i=lane;i<16*128;i+=32){
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncwarp(0xffffffffU);
    unsigned transcript_low=0,transcript_high=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    const unsigned *ap0=hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,0U+group,thread));
    const unsigned *ap1=hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,8U+group,thread));
    const unsigned *ap2=hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,16U+group,thread));
    const unsigned *ap3=hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,24U+group,thread));
    const unsigned *ap4=hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,32U+group,thread));
    for(unsigned offset=0;offset<32768;offset+=32){
        unsigned b0,b1,c0,c1;
        b_transpose6_fragments(cache,pb,offset,lane,b0,b1,c0,c1);
        {
            unsigned x0=ap0[0U];
            unsigned x1=ap1[0U];
            unsigned x2=ap0[4U];
            unsigned x3=ap1[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a0_0,a0_1,a0_2,a0_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a0_4,a0_5,a0_6,a0_7);
        }
        {
            unsigned x0=ap2[0U];
            unsigned x1=ap3[0U];
            unsigned x2=ap2[4U];
            unsigned x3=ap3[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a1_0,a1_1,a1_2,a1_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a1_4,a1_5,a1_6,a1_7);
        }
        {
            unsigned x0=ap4[0U];
            unsigned x1=0U;
            unsigned x2=ap4[4U];
            unsigned x3=0U;
            mma_accumulate(x0,x1,x2,x3,b0,b1,a2_0,a2_1,a2_2,a2_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a2_4,a2_5,a2_6,a2_7);
        }
        if((offset+32)%128==0){
            unsigned slot=((offset+32)/128-1)%16;
            unsigned low0=unsigned(a0_0)^unsigned(a0_1)^unsigned(a0_4)^unsigned(a0_5);
            unsigned high0=unsigned(a0_2)^unsigned(a0_3)^unsigned(a0_6)^unsigned(a0_7);
            unsigned low1=unsigned(a1_0)^unsigned(a1_1)^unsigned(a1_4)^unsigned(a1_5);
            unsigned high1=unsigned(a1_2)^unsigned(a1_3)^unsigned(a1_6)^unsigned(a1_7);
            unsigned low2=unsigned(a2_0)^unsigned(a2_1)^unsigned(a2_4)^unsigned(a2_5);
            unsigned high2=unsigned(a2_2)^unsigned(a2_3)^unsigned(a2_6)^unsigned(a2_7);
            unsigned v0=four_fold_value(0U,group,0U,low0,high0)^four_fold_value(1U,group,0U,low1,high1)^four_fold_value(2U,group,0U,low2,high2);
            unsigned v1=four_fold_value(0U,group,1U,low0,high0)^four_fold_value(1U,group,1U,low1,high1)^four_fold_value(2U,group,1U,low2,high2);
            unsigned v2=four_fold_value(0U,group,2U,low0,high0)^four_fold_value(1U,group,2U,low1,high1)^four_fold_value(2U,group,2U,low2,high2);
            unsigned v3=four_fold_value(0U,group,3U,low0,high0)^four_fold_value(1U,group,3U,low1,high1)^four_fold_value(2U,group,3U,low2,high2);
            partition_fold(v0,v1,v2,v3,lane,slot,transcript_low,transcript_high);
        }
        if(offset+32U<32768U){
            ap0+=8U;ap1+=8U;ap2+=8U;ap3+=8U;ap4+=8U;
        }
    }
    unsigned words0[16];
    unsigned words1[16];
    unsigned words2[16];
    unsigned words3[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i){
        if(active0)words0[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(0U,i));
        if(active1)words1[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(1U,i));
        if(active2)words2[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(2U,i));
        if(active3)words3[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(3U,i));
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
    if(active2)shared_b_emit(words2,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
    if(active3)shared_b_emit(words3,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
}

template<unsigned Steps>
__device__ __forceinline__ void combined_body(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    // Only block-uniform returns precede the block-wide validation reduction.
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&3U)||row_count>512||(row_count>32&&(row_count&31U))
            ||!column_count||column_count>16384||first>=row_count*column_count
            ||query_count>row_count*column_count-first)return;
    unsigned members=cta_group(row_count);
    unsigned block_ordinal=(first/members)*members+blockIdx.x*members;
    if(block_ordinal>=first+query_count)return;
    unsigned col=cta_tile_column(block_ordinal,column_count,row_count);
    unsigned block_row=cta_tile_row(block_ordinal,column_count,row_count);
    unsigned ordinal=block_ordinal+warp*4U,base=block_row+warp*4U;
    bool live=warp*4U<members&&ordinal<first+query_count&&ordinal+4U>first;
    const unsigned *cb=column_axes+col*32U;
    bool invalid=lane<16?cb[lane]>=n:false;
    // Validate even inactive quartets that exist in this block's row group.
    if(warp*4U<members){
        #pragma unroll
        for(unsigned t=0;t<4;++t)if(lane<10)invalid|=row_axes[(base+t)*32U+lane]>=m;
    }
    if(__syncthreads_or(invalid))return;
    bool active0=live&&ordinal>=first;
    bool active1=live&&ordinal+1>=first&&ordinal+1<first+query_count;
    bool active2=live&&ordinal+2>=first&&ordinal+2<first+query_count;
    bool active3=live&&ordinal+3>=first&&ordinal+3<first+query_count;
    __shared__ unsigned uniform_cache[6*128];
    __shared__ unsigned fragments[Steps*4*32];
    unsigned *cache=uniform_cache;
    for(unsigned i=threadIdx.x;i<16*128;i+=256){
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncthreads();
    unsigned transcript_low=0,transcript_high=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    const unsigned *ap0=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,0U+group,thread)):nullptr;
    const unsigned *ap1=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,8U+group,thread)):nullptr;
    const unsigned *ap2=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,16U+group,thread)):nullptr;
    const unsigned *ap3=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,24U+group,thread)):nullptr;
    const unsigned *ap4=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,32U+group,thread)):nullptr;

    for(unsigned chunk=0;chunk<32768;chunk+=Steps*32U){
        // All warps produce disjoint K fragments, including inactive consumers.
        #pragma unroll
        for(unsigned step=warp;step<Steps;step+=8U){
            unsigned b0,b1,c0,c1;
            b_transpose6_fragments(cache,pb,chunk+step*32U,lane,b0,b1,c0,c1);
            fragments[cta_fragment_index(step,0U,lane)]=b0;
            fragments[cta_fragment_index(step,1U,lane)]=b1;
            fragments[cta_fragment_index(step,2U,lane)]=c0;
            fragments[cta_fragment_index(step,3U,lane)]=c1;
        }
        __syncthreads();
        if(live){
            #pragma unroll 1
            for(unsigned step=0;step<Steps;++step){
                unsigned offset=chunk+step*32U;
                unsigned b0=fragments[cta_fragment_index(step,0U,lane)];
                unsigned b1=fragments[cta_fragment_index(step,1U,lane)];
                unsigned c0=fragments[cta_fragment_index(step,2U,lane)];
                unsigned c1=fragments[cta_fragment_index(step,3U,lane)];
        {
            unsigned x0=ap0[0U];
            unsigned x1=ap1[0U];
            unsigned x2=ap0[4U];
            unsigned x3=ap1[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a0_0,a0_1,a0_2,a0_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a0_4,a0_5,a0_6,a0_7);
        }
        {
            unsigned x0=ap2[0U];
            unsigned x1=ap3[0U];
            unsigned x2=ap2[4U];
            unsigned x3=ap3[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a1_0,a1_1,a1_2,a1_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a1_4,a1_5,a1_6,a1_7);
        }
        {
            unsigned x0=ap4[0U];
            unsigned x1=0U;
            unsigned x2=ap4[4U];
            unsigned x3=0U;
            mma_accumulate(x0,x1,x2,x3,b0,b1,a2_0,a2_1,a2_2,a2_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a2_4,a2_5,a2_6,a2_7);
        }
        if((offset+32)%128==0){
            unsigned slot=((offset+32)/128-1)%16;
            unsigned low0=unsigned(a0_0)^unsigned(a0_1)^unsigned(a0_4)^unsigned(a0_5);
            unsigned high0=unsigned(a0_2)^unsigned(a0_3)^unsigned(a0_6)^unsigned(a0_7);
            unsigned low1=unsigned(a1_0)^unsigned(a1_1)^unsigned(a1_4)^unsigned(a1_5);
            unsigned high1=unsigned(a1_2)^unsigned(a1_3)^unsigned(a1_6)^unsigned(a1_7);
            unsigned low2=unsigned(a2_0)^unsigned(a2_1)^unsigned(a2_4)^unsigned(a2_5);
            unsigned high2=unsigned(a2_2)^unsigned(a2_3)^unsigned(a2_6)^unsigned(a2_7);
            unsigned v0=four_fold_value(0U,group,0U,low0,high0)^four_fold_value(1U,group,0U,low1,high1)^four_fold_value(2U,group,0U,low2,high2);
            unsigned v1=four_fold_value(0U,group,1U,low0,high0)^four_fold_value(1U,group,1U,low1,high1)^four_fold_value(2U,group,1U,low2,high2);
            unsigned v2=four_fold_value(0U,group,2U,low0,high0)^four_fold_value(1U,group,2U,low1,high1)^four_fold_value(2U,group,2U,low2,high2);
            unsigned v3=four_fold_value(0U,group,3U,low0,high0)^four_fold_value(1U,group,3U,low1,high1)^four_fold_value(2U,group,3U,low2,high2);
            partition_fold(v0,v1,v2,v3,lane,slot,transcript_low,transcript_high);
        }
        if(offset+32U<32768U){
            ap0+=8U;ap1+=8U;ap2+=8U;ap3+=8U;ap4+=8U;
        }

            }
        }
        // Every consumer finishes before any producer overwrites the buffer.
        __syncthreads();
    }
    unsigned words0[16];
    unsigned words1[16];
    unsigned words2[16];
    unsigned words3[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i){
        if(active0)words0[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(0U,i));
        if(active1)words1[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(1U,i));
        if(active2)words2[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(2U,i));
        if(active3)words3[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source(3U,i));
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
    if(active2)shared_b_emit(words2,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
    if(active3)shared_b_emit(words3,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
}

extern "C" __global__ void combined_scan(PH_BQ_ARGS){combined_body<8>(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}

#undef PH_BQ_ARGS
