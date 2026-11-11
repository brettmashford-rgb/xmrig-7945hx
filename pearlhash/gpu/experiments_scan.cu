// ISC. Independent v073 block, pipeline and bounded-B experiments.
#include "cta_b_scan.cu"
#include "experiment_axes.h"
#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first


template<unsigned Steps>
__device__ __forceinline__ void small_body(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    // Only block-uniform returns precede the block-wide validation reduction.
    if(blockDim.x!=128||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&3U)||row_count>512||(row_count>16&&(row_count&15U))
            ||!column_count||column_count>16384||first>=row_count*column_count
            ||query_count>row_count*column_count-first)return;
    unsigned members=(row_count<16U?row_count:16U);
    unsigned block_ordinal=(first/members)*members+blockIdx.x*members;
    if(block_ordinal>=first+query_count)return;
    unsigned col=experiment_col(block_ordinal,column_count,row_count,16U);
    unsigned block_row=experiment_row(block_ordinal,column_count,row_count,16U);
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
    for(unsigned i=threadIdx.x;i<16*128;i+=128){
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncthreads();
    unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;
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
        for(unsigned step=warp;step<Steps;step+=4U){
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
            if(active0)four_fold(four_fold_value(0U,group,0U,low0,high0)^four_fold_value(1U,group,0U,low1,high1)^four_fold_value(2U,group,0U,low2,high2),lane,slot,word0);
            if(active1)four_fold(four_fold_value(0U,group,1U,low0,high0)^four_fold_value(1U,group,1U,low1,high1)^four_fold_value(2U,group,1U,low2,high2),lane,slot,word1);
            if(active2)four_fold(four_fold_value(0U,group,2U,low0,high0)^four_fold_value(1U,group,2U,low1,high1)^four_fold_value(2U,group,2U,low2,high2),lane,slot,word2);
            if(active3)four_fold(four_fold_value(0U,group,3U,low0,high0)^four_fold_value(1U,group,3U,low1,high1)^four_fold_value(2U,group,3U,low2,high2),lane,slot,word3);
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
        if(active0)words0[i]=__shfl_sync(0xffffffffU,word0,i);
        if(active1)words1[i]=__shfl_sync(0xffffffffU,word1,i);
        if(active2)words2[i]=__shfl_sync(0xffffffffU,word2,i);
        if(active3)words3[i]=__shfl_sync(0xffffffffU,word3,i);
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
    if(active2)shared_b_emit(words2,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
    if(active3)shared_b_emit(words3,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
}

extern "C" __global__ void small4_scan(PH_BQ_ARGS){small_body<4>(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}

extern "C" __global__ void small8_scan(PH_BQ_ARGS){small_body<8>(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}
__device__ __forceinline__ void pipeline_body(PH_BQ_ARGS) {
    unsigned physical=threadIdx.x/32,lane=threadIdx.x%32;
    bool consumer=physical>=2U;unsigned warp=consumer?physical-2U:0U;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    // Only block-uniform returns precede the block-wide validation reduction.
    if(blockDim.x!=320||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&3U)||row_count>512||(row_count>32&&(row_count&31U))
            ||!column_count||column_count>16384||first>=row_count*column_count
            ||query_count>row_count*column_count-first)return;
    unsigned members=cta_group(row_count);
    unsigned block_ordinal=(first/members)*members+blockIdx.x*members;
    if(block_ordinal>=first+query_count)return;
    unsigned col=cta_tile_column(block_ordinal,column_count,row_count);
    unsigned block_row=cta_tile_row(block_ordinal,column_count,row_count);
    unsigned ordinal=block_ordinal+warp*4U,base=block_row+warp*4U;
    bool live=consumer&&warp*4U<members&&ordinal<first+query_count&&ordinal+4U>first;
    const unsigned *cb=column_axes+col*32U;
    bool invalid=lane<16?cb[lane]>=n:false;
    // Validate even inactive quartets that exist in this block's row group.
    if(consumer&&warp*4U<members){
        #pragma unroll
        for(unsigned t=0;t<4;++t)if(lane<10)invalid|=row_axes[(base+t)*32U+lane]>=m;
    }
    if(__syncthreads_or(invalid))return;
    bool active0=live&&ordinal>=first;
    bool active1=live&&ordinal+1>=first&&ordinal+1<first+query_count;
    bool active2=live&&ordinal+2>=first&&ordinal+2<first+query_count;
    bool active3=live&&ordinal+3>=first&&ordinal+3<first+query_count;
    __shared__ unsigned uniform_cache[6*128];
    __shared__ unsigned fragments[2*8*4*32];
    unsigned *cache=uniform_cache;
    for(unsigned i=threadIdx.x;i<16*128;i+=320){
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncthreads();
    if(!consumer)for(unsigned step=physical;step<8U;step+=2U){
        unsigned b0,b1,c0,c1;b_transpose6_fragments(cache,pb,step*32U,lane,b0,b1,c0,c1);
        fragments[cta_fragment_index(step,0U,lane)]=b0;fragments[cta_fragment_index(step,1U,lane)]=b1;
        fragments[cta_fragment_index(step,2U,lane)]=c0;fragments[cta_fragment_index(step,3U,lane)]=c1;
    }
    __syncthreads();
    unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    const unsigned *ap0=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,0U+group,thread)):nullptr;
    const unsigned *ap1=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,8U+group,thread)):nullptr;
    const unsigned *ap2=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,16U+group,thread)):nullptr;
    const unsigned *ap3=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,24U+group,thread)):nullptr;
    const unsigned *ap4=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,32U+group,thread)):nullptr;

    unsigned current=0;
    for(unsigned chunk=0;chunk<32768U;chunk+=256U){
        if(!consumer&&chunk+256U<32768U)for(unsigned step=physical;step<8U;step+=2U){
            unsigned b0,b1,c0,c1;b_transpose6_fragments(cache,pb,chunk+256U+step*32U,lane,b0,b1,c0,c1);
            unsigned *next=fragments+(current^1U)*1024U;
            next[cta_fragment_index(step,0U,lane)]=b0;next[cta_fragment_index(step,1U,lane)]=b1;
            next[cta_fragment_index(step,2U,lane)]=c0;next[cta_fragment_index(step,3U,lane)]=c1;
        }
        if(live){
            #pragma unroll 1
            for(unsigned step=0;step<8U;++step){
                unsigned offset=chunk+step*32U;const unsigned *ready=fragments+current*1024U;
                unsigned b0=ready[cta_fragment_index(step,0U,lane)],b1=ready[cta_fragment_index(step,1U,lane)];
                unsigned c0=ready[cta_fragment_index(step,2U,lane)],c1=ready[cta_fragment_index(step,3U,lane)];
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
            if(active0)four_fold(four_fold_value(0U,group,0U,low0,high0)^four_fold_value(1U,group,0U,low1,high1)^four_fold_value(2U,group,0U,low2,high2),lane,slot,word0);
            if(active1)four_fold(four_fold_value(0U,group,1U,low0,high0)^four_fold_value(1U,group,1U,low1,high1)^four_fold_value(2U,group,1U,low2,high2),lane,slot,word1);
            if(active2)four_fold(four_fold_value(0U,group,2U,low0,high0)^four_fold_value(1U,group,2U,low1,high1)^four_fold_value(2U,group,2U,low2,high2),lane,slot,word2);
            if(active3)four_fold(four_fold_value(0U,group,3U,low0,high0)^four_fold_value(1U,group,3U,low1,high1)^four_fold_value(2U,group,3U,low2,high2),lane,slot,word3);
        }
        if(offset+32U<32768U){
            ap0+=8U;ap1+=8U;ap2+=8U;ap3+=8U;ap4+=8U;
        }

            }
        }
        __syncthreads();current^=1U;
    }
    unsigned words0[16];
    unsigned words1[16];
    unsigned words2[16];
    unsigned words3[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i){
        if(active0)words0[i]=__shfl_sync(0xffffffffU,word0,i);
        if(active1)words1[i]=__shfl_sync(0xffffffffU,word1,i);
        if(active2)words2[i]=__shfl_sync(0xffffffffU,word2,i);
        if(active3)words3[i]=__shfl_sync(0xffffffffU,word3,i);
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
    if(active2)shared_b_emit(words2,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
    if(active3)shared_b_emit(words3,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
}

extern "C" __global__ void pipeline_scan(PH_BQ_ARGS){pipeline_body(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}

extern "C" __global__ void build_b_panel(const signed char *ub,const unsigned *pb,const unsigned *columns,
        unsigned *out,unsigned width,unsigned n){
    unsigned col=blockIdx.x,lane=threadIdx.x%32,warp=threadIdx.x/32;
    if(blockDim.x!=256||!width||width>16||col>=width)return;
    const unsigned *cb=columns+col*32U;
    bool bad=threadIdx.x<16?cb[threadIdx.x]>=n:false;
    int invalid=__syncthreads_or(bad);
    if(threadIdx.x==0)out[col]=invalid?0U:1U;
    if(invalid)return;
    __shared__ unsigned cache[6*128];
    for(unsigned i=threadIdx.x;i<16*128;i+=256){unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*24+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);}
    __syncthreads();
    unsigned *fragments=out+28U+col*131072U;
    for(unsigned step=warp;step<1024U;step+=8U){
        unsigned b0,b1,c0,c1;b_transpose6_fragments(cache,pb,step*32U,lane,b0,b1,c0,c1);
        fragments[cta_fragment_index(step,0U,lane)]=b0;fragments[cta_fragment_index(step,1U,lane)]=b1;
        fragments[cta_fragment_index(step,2U,lane)]=c0;fragments[cta_fragment_index(step,3U,lane)]=c1;
    }
}
__device__ __forceinline__ void panel_body(PH_BQ_ARGS) {
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
    unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    const unsigned *ap0=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,0U+group,thread)):nullptr;
    const unsigned *ap1=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,8U+group,thread)):nullptr;
    const unsigned *ap2=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,16U+group,thread)):nullptr;
    const unsigned *ap3=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,24U+group,thread)):nullptr;
    const unsigned *ap4=live?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,32U+group,thread)):nullptr;

    const unsigned *fragments=reinterpret_cast<const unsigned*>(ub)+28U+col*131072U;
    for(unsigned offset=0;offset<32768U;offset+=32U){
        unsigned step=offset/32U;
        unsigned b0=fragments[cta_fragment_index(step,0U,lane)],b1=fragments[cta_fragment_index(step,1U,lane)];
        unsigned c0=fragments[cta_fragment_index(step,2U,lane)],c1=fragments[cta_fragment_index(step,3U,lane)];
        if(live){
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
            if(active0)four_fold(four_fold_value(0U,group,0U,low0,high0)^four_fold_value(1U,group,0U,low1,high1)^four_fold_value(2U,group,0U,low2,high2),lane,slot,word0);
            if(active1)four_fold(four_fold_value(0U,group,1U,low0,high0)^four_fold_value(1U,group,1U,low1,high1)^four_fold_value(2U,group,1U,low2,high2),lane,slot,word1);
            if(active2)four_fold(four_fold_value(0U,group,2U,low0,high0)^four_fold_value(1U,group,2U,low1,high1)^four_fold_value(2U,group,2U,low2,high2),lane,slot,word2);
            if(active3)four_fold(four_fold_value(0U,group,3U,low0,high0)^four_fold_value(1U,group,3U,low1,high1)^four_fold_value(2U,group,3U,low2,high2),lane,slot,word3);
        }
        if(offset+32U<32768U){
            ap0+=8U;ap1+=8U;ap2+=8U;ap3+=8U;ap4+=8U;
        }

        }
    }
    unsigned words0[16];
    unsigned words1[16];
    unsigned words2[16];
    unsigned words3[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i){
        if(active0)words0[i]=__shfl_sync(0xffffffffU,word0,i);
        if(active1)words1[i]=__shfl_sync(0xffffffffU,word1,i);
        if(active2)words2[i]=__shfl_sync(0xffffffffU,word2,i);
        if(active3)words3[i]=__shfl_sync(0xffffffffU,word3,i);
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
    if(active2)shared_b_emit(words2,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
    if(active3)shared_b_emit(words3,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
}

extern "C" __global__ void panel_scan(PH_BQ_ARGS){panel_body(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}

#undef PH_BQ_ARGS
