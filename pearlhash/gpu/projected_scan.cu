// ISC. Exact B-basis projection; scanner control remains byte-identical.
#include "a_share_scan.cu"
#include "projection_math.h"

extern "C" __global__ void projection_b_coeff(const unsigned *pb,signed char *low,short *special){
    unsigned q=blockIdx.x,t=threadIdx.x;
    if(blockDim.x!=128||q>=256)return;
    __shared__ int counts[128];counts[t]=0;if(!t)special[q]=-1;__syncthreads();
    unsigned pair=pb[q*128U+t];
    if(__syncthreads_or((pair&65535U)>=128U||(pair>>16)>=128U))return;
    atomicAdd(counts+(pair&65535U),1);atomicAdd(counts+(pair>>16),-1);__syncthreads();
    int v=counts[t];reinterpret_cast<unsigned char*>(low)[q*128U+t]=unsigned(v)&255U;
    // At most one positive coefficient can equal 128; -128 is representable.
    if(v==128)special[q]=short(t);
}

extern "C" __global__ void projection_b_sums(const signed char *ub,const signed char *coeff,
        const short *special,short *out,unsigned n){
    unsigned warp=blockIdx.x*4U+threadIdx.x/32U,lane=threadIdx.x%32U;
    unsigned total=((n+15U)/16U)*32U;
    if(blockDim.x!=128||warp>=total)return;
    unsigned group=lane/4U,thread=lane%4U,rb=(warp/32U)*16U,cb=(warp%32U)*8U;
    unsigned r0=rb+group,r1=r0+8U,c0=cb+thread*2U,c1=c0+1U;
    int d0=0,d1=0,d2=0,d3=0;
    for(unsigned k=0;k<128;k+=32){
        mma_accumulate(mma_pack4(ub,r0,n,128,k+thread*4U),mma_pack4(ub,r1,n,128,k+thread*4U),
            mma_pack4(ub,r0,n,128,k+thread*4U+16U),mma_pack4(ub,r1,n,128,k+thread*4U+16U),
            mma_pack4(coeff,cb+group,256,128,k+thread*4U),mma_pack4(coeff,cb+group,256,128,k+thread*4U+16U),d0,d1,d2,d3);
    }
    int s0=special[c0],s1=special[c1];
    if(r0<n){
        if(s0>=0)d0+=256*int(ub[r0*128U+unsigned(s0)]);
        if(s1>=0)d1+=256*int(ub[r0*128U+unsigned(s1)]);
        out[r0*256U+c0]=short(d0);out[r0*256U+c1]=short(d1);
    }
    if(r1<n){
        if(s0>=0)d2+=256*int(ub[r1*128U+unsigned(s0)]);
        if(s1>=0)d3+=256*int(ub[r1*128U+unsigned(s1)]);
        out[r1*256U+c0]=short(d2);out[r1*256U+c1]=short(d3);
    }
}

extern "C" __global__ void projection_prepare_a(const signed char *a,const unsigned *pb,signed char *low,
        short *row_sum,unsigned *counts,unsigned short *records,unsigned m){
    unsigned id=blockIdx.x,t=threadIdx.x;
    if(blockDim.x!=128||id>=m*256U)return;
    __shared__ int values[128];__shared__ int totals[4];__shared__ unsigned used;
    values[t]=0;if(!t)used=0;__syncthreads();
    unsigned pair=pb[(id%256U)*128U+t];
    bool invalid=(pair&65535U)>=128U||(pair>>16)>=128U;
    if(__syncthreads_or(invalid))return;
    int v=int(a[id*128U+t])-64;
    atomicAdd(values+(pair&65535U),v);atomicAdd(values+(pair>>16),-v);
    int sum=v;
    for(unsigned delta=16;delta;delta>>=1)sum+=__shfl_down_sync(0xffffffffU,sum,delta);
    if(!(t&31U))totals[t/32U]=sum;
    __syncthreads();
    if(!t)row_sum[id]=short(totals[0]+totals[1]+totals[2]+totals[3]);
    v=values[t];reinterpret_cast<unsigned char*>(low)[id*128U+t]=unsigned(v)&255U;
    int high=projection_high(v);
    if(high){unsigned slot=atomicAdd(&used,1U);records[id*128U+slot]=static_cast<unsigned short>(projection_record(t,high));}
    __syncthreads();if(!t)counts[id]=used;
}

__device__ __forceinline__ unsigned projection_uniform_word(const unsigned *cache,unsigned k,unsigned lane,unsigned side){
    unsigned group=lane/4U,thread=lane%4U,result=0;
    const unsigned char *bytes=reinterpret_cast<const unsigned char*>(cache);
    for(unsigned i=0;i<4;++i)result|=unsigned(bytes[(k+thread*4U+i)*24U+group+side*8U])<<(i*8U);
    return result;
}

__device__ __forceinline__ void projection_adjust(unsigned row,unsigned m,unsigned q,const unsigned *cb,
        unsigned local_col,const unsigned *cache,const short *asum,const unsigned *counts,
        const unsigned short *records,const short *bsum,int &d0,int &d1,int &d4,int &d5){
    if(row>=m)return;
    unsigned id=row*256U+q;
    int common=524288+64*int(asum[id]);
    d0+=common+64*int(bsum[cb[local_col]*256U+q]);
    d1+=common+64*int(bsum[cb[local_col+1U]*256U+q]);
    d4+=common+64*int(bsum[cb[local_col+8U]*256U+q]);
    d5+=common+64*int(bsum[cb[local_col+9U]*256U+q]);
    const signed char *bytes=reinterpret_cast<const signed char*>(cache);
    unsigned count=counts[id];
    for(unsigned i=0;i<count;++i){
        unsigned rec=records[id*128U+i],r=rec&127U;
        int high=projection_record_high(rec)*256;
        d0+=high*int(bytes[r*24U+local_col]);d1+=high*int(bytes[r*24U+local_col+1U]);
        d4+=high*int(bytes[r*24U+local_col+8U]);d5+=high*int(bytes[r*24U+local_col+9U]);
    }
}

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first, \
    const short *asum,const unsigned *correction_counts,const unsigned short *correction_records,const short *bsum


__device__ __forceinline__ void projected_pair_body(PH_BQ_ARGS) {
    constexpr unsigned Steps=4;
    constexpr bool ShareA=false;
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32,column_lane=warp&1U,quartet=warp/2U;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&3U)||row_count>512||(row_count>16&&(row_count&15U))
            ||!column_count||column_count>16384||first>=row_count*column_count
            ||!query_count||query_count>row_count*column_count-first)return;
    unsigned members=a_pair_members(row_count);
    unsigned block=a_pair_block(first,row_count,column_count)+blockIdx.x;
    unsigned block_ordinal=a_pair_first(block,row_count,column_count);
    if(block_ordinal>=first+query_count)return;
    unsigned col=a_pair_col_base(block,column_count),width=(col+1U<column_count?2U:1U);
    unsigned block_row=a_pair_row_base(block,row_count,column_count);
    unsigned ordinal=block_ordinal+column_lane*members+quartet*4U,base=block_row+quartet*4U;
    bool rows_exist=quartet*4U<members,column_exists=column_lane<width;
    bool live=rows_exist&&column_exists&&ordinal<first+query_count&&ordinal+4U>first;
    const unsigned *cb=column_axes+(col+(column_exists?column_lane:0U))*32U;
    bool invalid=column_exists&&lane<16?cb[lane]>=n:false;
    if(rows_exist){
        #pragma unroll
        for(unsigned tile=0;tile<4;++tile)if(lane<10)invalid|=row_axes[(base+tile)*32U+lane]>=m;
    }
    if(__syncthreads_or(invalid))return;
    bool active0=live&&ordinal>=first;
    bool active1=live&&ordinal+1>=first&&ordinal+1<first+query_count;
    bool active2=live&&ordinal+2>=first&&ordinal+2<first+query_count;
    bool active3=live&&ordinal+3>=first&&ordinal+3<first+query_count;
    // A producer must stay active even when only its paired column is requested.
    bool a_loader=rows_exist&&(ShareA?column_lane==0U:live);
    __shared__ unsigned uniform_cache[2][6*128];
    __shared__ unsigned fragments[2*Steps*4*32];
    __shared__ unsigned a_stage[ShareA?4*Steps*10*32:1];
    for(unsigned i=threadIdx.x;i<2U*16U*128U;i+=256U){
        unsigned side=i/(16U*128U),r=(i/128U)%16U,index=i%128U;
        unsigned char value=0;
        if(side<width)value=static_cast<unsigned char>(ub[column_axes[(col+side)*32U+r]*128U+index]);
        reinterpret_cast<unsigned char*>(uniform_cache[side])[index*6U*4U+r]=value;
    }
    __syncthreads();
    unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;
    int a0_0=0,a0_1=0,a0_2=0,a0_3=0,a0_4=0,a0_5=0,a0_6=0,a0_7=0;
    int a1_0=0,a1_1=0,a1_2=0,a1_3=0,a1_4=0,a1_5=0,a1_6=0,a1_7=0;
    int a2_0=0,a2_1=0,a2_2=0,a2_3=0,a2_4=0,a2_5=0,a2_6=0,a2_7=0;
    const unsigned *ap0=a_loader?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,0U+group,thread)):nullptr;
    const unsigned *ap1=a_loader?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,8U+group,thread)):nullptr;
    const unsigned *ap2=a_loader?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,16U+group,thread)):nullptr;
    const unsigned *ap3=a_loader?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,24U+group,thread)):nullptr;
    const unsigned *ap4=a_loader?hoisted_a_pointer(ua,hoisted_a_base(row_axes,base,32U+group,thread)):nullptr;

    unsigned producer_column=warp/4U,producer_step=warp%4U;
    unsigned b0=0,b1=0,c0=0,c1=0;
    if(producer_column<width){
        b0=projection_uniform_word(uniform_cache[producer_column],producer_step*32U,lane,0);
        b1=projection_uniform_word(uniform_cache[producer_column],producer_step*32U+16U,lane,0);
        c0=projection_uniform_word(uniform_cache[producer_column],producer_step*32U,lane,1);
        c1=projection_uniform_word(uniform_cache[producer_column],producer_step*32U+16U,lane,1);
    }
    fragments[a_pair_b_index(producer_column,producer_step,0U,lane)]=b0;
    fragments[a_pair_b_index(producer_column,producer_step,1U,lane)]=b1;
    fragments[a_pair_b_index(producer_column,producer_step,2U,lane)]=c0;
    fragments[a_pair_b_index(producer_column,producer_step,3U,lane)]=c1;
    __syncthreads();
    unsigned ar0=hoisted_a_base(row_axes,base,0U+group,thread)/8192U;
    unsigned ar1=hoisted_a_base(row_axes,base,8U+group,thread)/8192U;
    unsigned ar2=hoisted_a_base(row_axes,base,16U+group,thread)/8192U;
    unsigned ar3=hoisted_a_base(row_axes,base,24U+group,thread)/8192U;
    unsigned ar4=hoisted_a_base(row_axes,base,32U+group,thread)/8192U;
    for(unsigned chunk=0;chunk<32768;chunk+=Steps*32U){
        if(live){
            #pragma unroll 1
            for(unsigned step=0;step<Steps;++step){
                unsigned offset=chunk+step*32U;
                unsigned b0=fragments[a_pair_b_index(column_lane,step,0U,lane)];
                unsigned b1=fragments[a_pair_b_index(column_lane,step,1U,lane)];
                unsigned c0=fragments[a_pair_b_index(column_lane,step,2U,lane)];
                unsigned c1=fragments[a_pair_b_index(column_lane,step,3U,lane)];
        {
            unsigned x0=ShareA?a_stage[a_share_index(quartet,step,0U,lane)]:ap0[0U];
            unsigned x1=ShareA?a_stage[a_share_index(quartet,step,1U,lane)]:ap1[0U];
            unsigned x2=ShareA?a_stage[a_share_index(quartet,step,2U,lane)]:ap0[4U];
            unsigned x3=ShareA?a_stage[a_share_index(quartet,step,3U,lane)]:ap1[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a0_0,a0_1,a0_2,a0_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a0_4,a0_5,a0_6,a0_7);
        }
        {
            unsigned x0=ShareA?a_stage[a_share_index(quartet,step,4U,lane)]:ap2[0U];
            unsigned x1=ShareA?a_stage[a_share_index(quartet,step,5U,lane)]:ap3[0U];
            unsigned x2=ShareA?a_stage[a_share_index(quartet,step,6U,lane)]:ap2[4U];
            unsigned x3=ShareA?a_stage[a_share_index(quartet,step,7U,lane)]:ap3[4U];
            mma_accumulate(x0,x1,x2,x3,b0,b1,a1_0,a1_1,a1_2,a1_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a1_4,a1_5,a1_6,a1_7);
        }
        {
            unsigned x0=ShareA?a_stage[a_share_index(quartet,step,8U,lane)]:ap4[0U];
            unsigned x1=0U;
            unsigned x2=ShareA?a_stage[a_share_index(quartet,step,9U,lane)]:ap4[4U];
            unsigned x3=0U;
            mma_accumulate(x0,x1,x2,x3,b0,b1,a2_0,a2_1,a2_2,a2_3);
            mma_accumulate(x0,x1,x2,x3,c0,c1,a2_4,a2_5,a2_6,a2_7);
        }
        if((offset+32)%128==0){
            unsigned q=(offset+32U)/128U-1U;
            projection_adjust(ar0,m,q,cb,thread*2U,uniform_cache[column_lane],asum,correction_counts,correction_records,bsum,a0_0,a0_1,a0_4,a0_5);
            projection_adjust(ar1,m,q,cb,thread*2U,uniform_cache[column_lane],asum,correction_counts,correction_records,bsum,a0_2,a0_3,a0_6,a0_7);
            projection_adjust(ar2,m,q,cb,thread*2U,uniform_cache[column_lane],asum,correction_counts,correction_records,bsum,a1_0,a1_1,a1_4,a1_5);
            projection_adjust(ar3,m,q,cb,thread*2U,uniform_cache[column_lane],asum,correction_counts,correction_records,bsum,a1_2,a1_3,a1_6,a1_7);
            projection_adjust(ar4,m,q,cb,thread*2U,uniform_cache[column_lane],asum,correction_counts,correction_records,bsum,a2_0,a2_1,a2_4,a2_5);
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
        if(!ShareA&&offset+32U<32768U){
            ap0+=8U;ap1+=8U;ap2+=8U;ap3+=8U;ap4+=8U;
        }

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

extern "C" __global__ void projected_pair_scan(PH_BQ_ARGS){projected_pair_body(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first,asum,correction_counts,correction_records,bsum);}
#undef PH_BQ_ARGS
