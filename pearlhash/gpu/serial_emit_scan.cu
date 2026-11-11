// ISC. Retain v066 packed control; gather/hash/emit one transcript at a time.
#include "four_tile_scan.cu"

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first

__device__ __forceinline__ void serial_redux_fold(unsigned value,unsigned lane,unsigned slot,unsigned &word){
    asm volatile("redux.sync.xor.b32 %0, %1, 0xffffffff;" : "=r"(value) : "r"(value));
    if(lane==slot)word=((word<<13)|(word>>19))^value;
}
extern "C" __global__ void serial_emit_scan(PH_BQ_ARGS) {
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
    unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    for(unsigned offset=0;offset<32768;offset+=32){
        unsigned b0,b1,c0,c1;
        b_transpose6_fragments(cache,pb,offset,lane,b0,b1,c0,c1);
        {
            unsigned x0=four_a_word(ua,row_axes,base,0U+group,offset+thread*4U+0U);
            unsigned x1=four_a_word(ua,row_axes,base,8U+group,offset+thread*4U+0U);
            unsigned x2=four_a_word(ua,row_axes,base,0U+group,offset+thread*4U+16U);
            unsigned x3=four_a_word(ua,row_axes,base,8U+group,offset+thread*4U+16U);
            mma_accumulate(x0,x1,x2,x3,b0,b1,a0_0,a0_1,a0_2,a0_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a0_4,a0_5,a0_6,a0_7);
        }
        {
            unsigned x0=four_a_word(ua,row_axes,base,16U+group,offset+thread*4U+0U);
            unsigned x1=four_a_word(ua,row_axes,base,24U+group,offset+thread*4U+0U);
            unsigned x2=four_a_word(ua,row_axes,base,16U+group,offset+thread*4U+16U);
            unsigned x3=four_a_word(ua,row_axes,base,24U+group,offset+thread*4U+16U);
            mma_accumulate(x0,x1,x2,x3,b0,b1,a1_0,a1_1,a1_2,a1_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a1_4,a1_5,a1_6,a1_7);
        }
        {
            unsigned x0=four_a_word(ua,row_axes,base,32U+group,offset+thread*4U+0U);
            unsigned x1=four_a_word(ua,row_axes,base,40U+group,offset+thread*4U+0U);
            unsigned x2=four_a_word(ua,row_axes,base,32U+group,offset+thread*4U+16U);
            unsigned x3=four_a_word(ua,row_axes,base,40U+group,offset+thread*4U+16U);
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
    }
    if(active0){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word0,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active1){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word1,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active2){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word2,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active3){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word3,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
        __syncwarp(0xffffffffU);
    }
}

extern "C" __global__ void serial_emit_redux_scan(PH_BQ_ARGS) {
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
    unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    for(unsigned offset=0;offset<32768;offset+=32){
        unsigned b0,b1,c0,c1;
        b_transpose6_fragments(cache,pb,offset,lane,b0,b1,c0,c1);
        {
            unsigned x0=four_a_word(ua,row_axes,base,0U+group,offset+thread*4U+0U);
            unsigned x1=four_a_word(ua,row_axes,base,8U+group,offset+thread*4U+0U);
            unsigned x2=four_a_word(ua,row_axes,base,0U+group,offset+thread*4U+16U);
            unsigned x3=four_a_word(ua,row_axes,base,8U+group,offset+thread*4U+16U);
            mma_accumulate(x0,x1,x2,x3,b0,b1,a0_0,a0_1,a0_2,a0_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a0_4,a0_5,a0_6,a0_7);
        }
        {
            unsigned x0=four_a_word(ua,row_axes,base,16U+group,offset+thread*4U+0U);
            unsigned x1=four_a_word(ua,row_axes,base,24U+group,offset+thread*4U+0U);
            unsigned x2=four_a_word(ua,row_axes,base,16U+group,offset+thread*4U+16U);
            unsigned x3=four_a_word(ua,row_axes,base,24U+group,offset+thread*4U+16U);
            mma_accumulate(x0,x1,x2,x3,b0,b1,a1_0,a1_1,a1_2,a1_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a1_4,a1_5,a1_6,a1_7);
        }
        {
            unsigned x0=four_a_word(ua,row_axes,base,32U+group,offset+thread*4U+0U);
            unsigned x1=four_a_word(ua,row_axes,base,40U+group,offset+thread*4U+0U);
            unsigned x2=four_a_word(ua,row_axes,base,32U+group,offset+thread*4U+16U);
            unsigned x3=four_a_word(ua,row_axes,base,40U+group,offset+thread*4U+16U);
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
            if(active0)serial_redux_fold(four_fold_value(0U,group,0U,low0,high0)^four_fold_value(1U,group,0U,low1,high1)^four_fold_value(2U,group,0U,low2,high2),lane,slot,word0);
            if(active1)serial_redux_fold(four_fold_value(0U,group,1U,low0,high0)^four_fold_value(1U,group,1U,low1,high1)^four_fold_value(2U,group,1U,low2,high2),lane,slot,word1);
            if(active2)serial_redux_fold(four_fold_value(0U,group,2U,low0,high0)^four_fold_value(1U,group,2U,low1,high1)^four_fold_value(2U,group,2U,low2,high2),lane,slot,word2);
            if(active3)serial_redux_fold(four_fold_value(0U,group,3U,low0,high0)^four_fold_value(1U,group,3U,low1,high1)^four_fold_value(2U,group,3U,low2,high2),lane,slot,word3);
        }
    }
    if(active0){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word0,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active1){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word1,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active2){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word2,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active3){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word3,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
        __syncwarp(0xffffffffU);
    }
}

#undef PH_BQ_ARGS
