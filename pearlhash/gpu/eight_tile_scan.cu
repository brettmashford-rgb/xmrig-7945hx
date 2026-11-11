// ISC. v068 pointer control plus five-slab 80-row octets sharing one B reconstruction.
#include "hoisted_a_scan.cu"
#include "eight_tile_axes.h"

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first

__device__ __forceinline__ const unsigned *eight_a_pointer(const signed char *input,const unsigned *axes,unsigned base,unsigned packed_row,unsigned thread){
    unsigned row=axes[(base+eight_packed_tile(packed_row))*32U+eight_packed_row(packed_row)];
    return reinterpret_cast<const unsigned*>(input)+row*8192U+thread;
}

extern "C" __global__ void eight_tile_packed_scan(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&7U)||row_count>512||!column_count||column_count>16384
            ||first>=row_count*column_count||query_count>row_count*column_count-first)return;
    unsigned ordinal=(first&~7U)+(blockIdx.x*8+warp)*8U;
    if(ordinal>=first+query_count)return;
    unsigned base=eight_tile_row(ordinal,column_count),col=eight_tile_column(ordinal,column_count);
    const unsigned *cb=column_axes+col*32U;
    bool invalid=lane<16?cb[lane]>=n:false;
    #pragma unroll
    for(unsigned t=0;t<8;++t)if(lane<10)invalid|=row_axes[(base+t)*32U+lane]>=m;
    if(__any_sync(0xffffffffU,invalid))return;
    bool active0=ordinal+0U>=first&&ordinal+0U<first+query_count;
    bool active1=ordinal+1U>=first&&ordinal+1U<first+query_count;
    bool active2=ordinal+2U>=first&&ordinal+2U<first+query_count;
    bool active3=ordinal+3U>=first&&ordinal+3U<first+query_count;
    bool active4=ordinal+4U>=first&&ordinal+4U<first+query_count;
    bool active5=ordinal+5U>=first&&ordinal+5U<first+query_count;
    bool active6=ordinal+6U>=first&&ordinal+6U<first+query_count;
    bool active7=ordinal+7U>=first&&ordinal+7U<first+query_count;
    __shared__ unsigned uniform_cache[8][6*128];
    unsigned *cache=uniform_cache[warp];
    for(unsigned i=lane;i<16*128;i+=32){
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncwarp(0xffffffffU);
    unsigned word0=0,word1=0,word2=0,word3=0,word4=0,word5=0,word6=0,word7=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    int a3_0=0,a3_1=0,a3_2=0,a3_3=0,a3_4=0,a3_5=0,a3_6=0,a3_7=0;
    int a4_0=0,a4_1=0,a4_2=0,a4_3=0,a4_4=0,a4_5=0,a4_6=0,a4_7=0;
    const unsigned *ap0=eight_a_pointer(ua,row_axes,base,0U+group,thread);
    const unsigned *ap1=eight_a_pointer(ua,row_axes,base,8U+group,thread);
    const unsigned *ap2=eight_a_pointer(ua,row_axes,base,16U+group,thread);
    const unsigned *ap3=eight_a_pointer(ua,row_axes,base,24U+group,thread);
    const unsigned *ap4=eight_a_pointer(ua,row_axes,base,32U+group,thread);
    const unsigned *ap5=eight_a_pointer(ua,row_axes,base,40U+group,thread);
    const unsigned *ap6=eight_a_pointer(ua,row_axes,base,48U+group,thread);
    const unsigned *ap7=eight_a_pointer(ua,row_axes,base,56U+group,thread);
    const unsigned *ap8=eight_a_pointer(ua,row_axes,base,64U+group,thread);
    const unsigned *ap9=eight_a_pointer(ua,row_axes,base,72U+group,thread);
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
            unsigned x1=ap5[0U];
            unsigned x2=ap4[4U];
            unsigned x3=ap5[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a2_0,a2_1,a2_2,a2_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a2_4,a2_5,a2_6,a2_7);
        }
        {
            unsigned x0=ap6[0U];
            unsigned x1=ap7[0U];
            unsigned x2=ap6[4U];
            unsigned x3=ap7[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a3_0,a3_1,a3_2,a3_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a3_4,a3_5,a3_6,a3_7);
        }
        {
            unsigned x0=ap8[0U];
            unsigned x1=ap9[0U];
            unsigned x2=ap8[4U];
            unsigned x3=ap9[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a4_0,a4_1,a4_2,a4_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a4_4,a4_5,a4_6,a4_7);
        }
        if((offset+32)%128==0){
            unsigned slot=((offset+32)/128-1)%16;
            unsigned low0=unsigned(a0_0)^unsigned(a0_1)^unsigned(a0_4)^unsigned(a0_5);
            unsigned high0=unsigned(a0_2)^unsigned(a0_3)^unsigned(a0_6)^unsigned(a0_7);
            unsigned low1=unsigned(a1_0)^unsigned(a1_1)^unsigned(a1_4)^unsigned(a1_5);
            unsigned high1=unsigned(a1_2)^unsigned(a1_3)^unsigned(a1_6)^unsigned(a1_7);
            unsigned low2=unsigned(a2_0)^unsigned(a2_1)^unsigned(a2_4)^unsigned(a2_5);
            unsigned high2=unsigned(a2_2)^unsigned(a2_3)^unsigned(a2_6)^unsigned(a2_7);
            unsigned low3=unsigned(a3_0)^unsigned(a3_1)^unsigned(a3_4)^unsigned(a3_5);
            unsigned high3=unsigned(a3_2)^unsigned(a3_3)^unsigned(a3_6)^unsigned(a3_7);
            unsigned low4=unsigned(a4_0)^unsigned(a4_1)^unsigned(a4_4)^unsigned(a4_5);
            unsigned high4=unsigned(a4_2)^unsigned(a4_3)^unsigned(a4_6)^unsigned(a4_7);
            if(active0)four_fold(eight_fold_value(0U,group,0U,low0,high0)^eight_fold_value(1U,group,0U,low1,high1)^eight_fold_value(2U,group,0U,low2,high2)^eight_fold_value(3U,group,0U,low3,high3)^eight_fold_value(4U,group,0U,low4,high4),lane,slot,word0);
            if(active1)four_fold(eight_fold_value(0U,group,1U,low0,high0)^eight_fold_value(1U,group,1U,low1,high1)^eight_fold_value(2U,group,1U,low2,high2)^eight_fold_value(3U,group,1U,low3,high3)^eight_fold_value(4U,group,1U,low4,high4),lane,slot,word1);
            if(active2)four_fold(eight_fold_value(0U,group,2U,low0,high0)^eight_fold_value(1U,group,2U,low1,high1)^eight_fold_value(2U,group,2U,low2,high2)^eight_fold_value(3U,group,2U,low3,high3)^eight_fold_value(4U,group,2U,low4,high4),lane,slot,word2);
            if(active3)four_fold(eight_fold_value(0U,group,3U,low0,high0)^eight_fold_value(1U,group,3U,low1,high1)^eight_fold_value(2U,group,3U,low2,high2)^eight_fold_value(3U,group,3U,low3,high3)^eight_fold_value(4U,group,3U,low4,high4),lane,slot,word3);
            if(active4)four_fold(eight_fold_value(0U,group,4U,low0,high0)^eight_fold_value(1U,group,4U,low1,high1)^eight_fold_value(2U,group,4U,low2,high2)^eight_fold_value(3U,group,4U,low3,high3)^eight_fold_value(4U,group,4U,low4,high4),lane,slot,word4);
            if(active5)four_fold(eight_fold_value(0U,group,5U,low0,high0)^eight_fold_value(1U,group,5U,low1,high1)^eight_fold_value(2U,group,5U,low2,high2)^eight_fold_value(3U,group,5U,low3,high3)^eight_fold_value(4U,group,5U,low4,high4),lane,slot,word5);
            if(active6)four_fold(eight_fold_value(0U,group,6U,low0,high0)^eight_fold_value(1U,group,6U,low1,high1)^eight_fold_value(2U,group,6U,low2,high2)^eight_fold_value(3U,group,6U,low3,high3)^eight_fold_value(4U,group,6U,low4,high4),lane,slot,word6);
            if(active7)four_fold(eight_fold_value(0U,group,7U,low0,high0)^eight_fold_value(1U,group,7U,low1,high1)^eight_fold_value(2U,group,7U,low2,high2)^eight_fold_value(3U,group,7U,low3,high3)^eight_fold_value(4U,group,7U,low4,high4),lane,slot,word7);
        }
        if(offset+32U<32768U){
            ap0+=8U;
            ap1+=8U;
            ap2+=8U;
            ap3+=8U;
            ap4+=8U;
            ap5+=8U;
            ap6+=8U;
            ap7+=8U;
            ap8+=8U;
            ap9+=8U;
        }
    }
    unsigned words0[16];
    unsigned words1[16];
    unsigned words2[16];
    unsigned words3[16];
    unsigned words4[16];
    unsigned words5[16];
    unsigned words6[16];
    unsigned words7[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i){
        if(active0)words0[i]=__shfl_sync(0xffffffffU,word0,i);
        if(active1)words1[i]=__shfl_sync(0xffffffffU,word1,i);
        if(active2)words2[i]=__shfl_sync(0xffffffffU,word2,i);
        if(active3)words3[i]=__shfl_sync(0xffffffffU,word3,i);
        if(active4)words4[i]=__shfl_sync(0xffffffffU,word4,i);
        if(active5)words5[i]=__shfl_sync(0xffffffffU,word5,i);
        if(active6)words6[i]=__shfl_sync(0xffffffffU,word6,i);
        if(active7)words7[i]=__shfl_sync(0xffffffffU,word7,i);
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+0U-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1U-first,generation);
    if(active2)shared_b_emit(words2,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+2U-first,generation);
    if(active3)shared_b_emit(words3,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+3U-first,generation);
    if(active4)shared_b_emit(words4,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+4U-first,generation);
    if(active5)shared_b_emit(words5,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+5U-first,generation);
    if(active6)shared_b_emit(words6,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+6U-first,generation);
    if(active7)shared_b_emit(words7,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+7U-first,generation);
}

extern "C" __global__ void eight_tile_serial_scan(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&7U)||row_count>512||!column_count||column_count>16384
            ||first>=row_count*column_count||query_count>row_count*column_count-first)return;
    unsigned ordinal=(first&~7U)+(blockIdx.x*8+warp)*8U;
    if(ordinal>=first+query_count)return;
    unsigned base=eight_tile_row(ordinal,column_count),col=eight_tile_column(ordinal,column_count);
    const unsigned *cb=column_axes+col*32U;
    bool invalid=lane<16?cb[lane]>=n:false;
    #pragma unroll
    for(unsigned t=0;t<8;++t)if(lane<10)invalid|=row_axes[(base+t)*32U+lane]>=m;
    if(__any_sync(0xffffffffU,invalid))return;
    bool active0=ordinal+0U>=first&&ordinal+0U<first+query_count;
    bool active1=ordinal+1U>=first&&ordinal+1U<first+query_count;
    bool active2=ordinal+2U>=first&&ordinal+2U<first+query_count;
    bool active3=ordinal+3U>=first&&ordinal+3U<first+query_count;
    bool active4=ordinal+4U>=first&&ordinal+4U<first+query_count;
    bool active5=ordinal+5U>=first&&ordinal+5U<first+query_count;
    bool active6=ordinal+6U>=first&&ordinal+6U<first+query_count;
    bool active7=ordinal+7U>=first&&ordinal+7U<first+query_count;
    __shared__ unsigned uniform_cache[8][6*128];
    unsigned *cache=uniform_cache[warp];
    for(unsigned i=lane;i<16*128;i+=32){
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncwarp(0xffffffffU);
    unsigned word0=0,word1=0,word2=0,word3=0,word4=0,word5=0,word6=0,word7=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    int a3_0=0,a3_1=0,a3_2=0,a3_3=0,a3_4=0,a3_5=0,a3_6=0,a3_7=0;
    int a4_0=0,a4_1=0,a4_2=0,a4_3=0,a4_4=0,a4_5=0,a4_6=0,a4_7=0;
    const unsigned *ap0=eight_a_pointer(ua,row_axes,base,0U+group,thread);
    const unsigned *ap1=eight_a_pointer(ua,row_axes,base,8U+group,thread);
    const unsigned *ap2=eight_a_pointer(ua,row_axes,base,16U+group,thread);
    const unsigned *ap3=eight_a_pointer(ua,row_axes,base,24U+group,thread);
    const unsigned *ap4=eight_a_pointer(ua,row_axes,base,32U+group,thread);
    const unsigned *ap5=eight_a_pointer(ua,row_axes,base,40U+group,thread);
    const unsigned *ap6=eight_a_pointer(ua,row_axes,base,48U+group,thread);
    const unsigned *ap7=eight_a_pointer(ua,row_axes,base,56U+group,thread);
    const unsigned *ap8=eight_a_pointer(ua,row_axes,base,64U+group,thread);
    const unsigned *ap9=eight_a_pointer(ua,row_axes,base,72U+group,thread);
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
            unsigned x1=ap5[0U];
            unsigned x2=ap4[4U];
            unsigned x3=ap5[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a2_0,a2_1,a2_2,a2_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a2_4,a2_5,a2_6,a2_7);
        }
        {
            unsigned x0=ap6[0U];
            unsigned x1=ap7[0U];
            unsigned x2=ap6[4U];
            unsigned x3=ap7[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a3_0,a3_1,a3_2,a3_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a3_4,a3_5,a3_6,a3_7);
        }
        {
            unsigned x0=ap8[0U];
            unsigned x1=ap9[0U];
            unsigned x2=ap8[4U];
            unsigned x3=ap9[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a4_0,a4_1,a4_2,a4_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a4_4,a4_5,a4_6,a4_7);
        }
        if((offset+32)%128==0){
            unsigned slot=((offset+32)/128-1)%16;
            unsigned low0=unsigned(a0_0)^unsigned(a0_1)^unsigned(a0_4)^unsigned(a0_5);
            unsigned high0=unsigned(a0_2)^unsigned(a0_3)^unsigned(a0_6)^unsigned(a0_7);
            unsigned low1=unsigned(a1_0)^unsigned(a1_1)^unsigned(a1_4)^unsigned(a1_5);
            unsigned high1=unsigned(a1_2)^unsigned(a1_3)^unsigned(a1_6)^unsigned(a1_7);
            unsigned low2=unsigned(a2_0)^unsigned(a2_1)^unsigned(a2_4)^unsigned(a2_5);
            unsigned high2=unsigned(a2_2)^unsigned(a2_3)^unsigned(a2_6)^unsigned(a2_7);
            unsigned low3=unsigned(a3_0)^unsigned(a3_1)^unsigned(a3_4)^unsigned(a3_5);
            unsigned high3=unsigned(a3_2)^unsigned(a3_3)^unsigned(a3_6)^unsigned(a3_7);
            unsigned low4=unsigned(a4_0)^unsigned(a4_1)^unsigned(a4_4)^unsigned(a4_5);
            unsigned high4=unsigned(a4_2)^unsigned(a4_3)^unsigned(a4_6)^unsigned(a4_7);
            if(active0)four_fold(eight_fold_value(0U,group,0U,low0,high0)^eight_fold_value(1U,group,0U,low1,high1)^eight_fold_value(2U,group,0U,low2,high2)^eight_fold_value(3U,group,0U,low3,high3)^eight_fold_value(4U,group,0U,low4,high4),lane,slot,word0);
            if(active1)four_fold(eight_fold_value(0U,group,1U,low0,high0)^eight_fold_value(1U,group,1U,low1,high1)^eight_fold_value(2U,group,1U,low2,high2)^eight_fold_value(3U,group,1U,low3,high3)^eight_fold_value(4U,group,1U,low4,high4),lane,slot,word1);
            if(active2)four_fold(eight_fold_value(0U,group,2U,low0,high0)^eight_fold_value(1U,group,2U,low1,high1)^eight_fold_value(2U,group,2U,low2,high2)^eight_fold_value(3U,group,2U,low3,high3)^eight_fold_value(4U,group,2U,low4,high4),lane,slot,word2);
            if(active3)four_fold(eight_fold_value(0U,group,3U,low0,high0)^eight_fold_value(1U,group,3U,low1,high1)^eight_fold_value(2U,group,3U,low2,high2)^eight_fold_value(3U,group,3U,low3,high3)^eight_fold_value(4U,group,3U,low4,high4),lane,slot,word3);
            if(active4)four_fold(eight_fold_value(0U,group,4U,low0,high0)^eight_fold_value(1U,group,4U,low1,high1)^eight_fold_value(2U,group,4U,low2,high2)^eight_fold_value(3U,group,4U,low3,high3)^eight_fold_value(4U,group,4U,low4,high4),lane,slot,word4);
            if(active5)four_fold(eight_fold_value(0U,group,5U,low0,high0)^eight_fold_value(1U,group,5U,low1,high1)^eight_fold_value(2U,group,5U,low2,high2)^eight_fold_value(3U,group,5U,low3,high3)^eight_fold_value(4U,group,5U,low4,high4),lane,slot,word5);
            if(active6)four_fold(eight_fold_value(0U,group,6U,low0,high0)^eight_fold_value(1U,group,6U,low1,high1)^eight_fold_value(2U,group,6U,low2,high2)^eight_fold_value(3U,group,6U,low3,high3)^eight_fold_value(4U,group,6U,low4,high4),lane,slot,word6);
            if(active7)four_fold(eight_fold_value(0U,group,7U,low0,high0)^eight_fold_value(1U,group,7U,low1,high1)^eight_fold_value(2U,group,7U,low2,high2)^eight_fold_value(3U,group,7U,low3,high3)^eight_fold_value(4U,group,7U,low4,high4),lane,slot,word7);
        }
        if(offset+32U<32768U){
            ap0+=8U;
            ap1+=8U;
            ap2+=8U;
            ap3+=8U;
            ap4+=8U;
            ap5+=8U;
            ap6+=8U;
            ap7+=8U;
            ap8+=8U;
            ap9+=8U;
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
    if(active4){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word4,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+4U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active5){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word5,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+5U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active6){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word6,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+6U-first,generation);
        __syncwarp(0xffffffffU);
    }
    if(active7){
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word7,i);
        if(lane==0)shared_b_emit(words,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+7U-first,generation);
        __syncwarp(0xffffffffU);
    }
}

#undef PH_BQ_ARGS
