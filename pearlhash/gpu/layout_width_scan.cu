// ISC. v081 equal-work CTA aspect ratios, four K32 steps per stage.
#include "a_share_scan.cu"
#include "pair_depth_axes.h"
#include "layout_width_axes.h"
#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first


template<unsigned Columns>
__device__ __forceinline__ void layout_width_body(PH_BQ_ARGS) {
    constexpr bool ShareA=false;
    constexpr unsigned Steps=4;
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32,column_lane=warp%Columns,quartet=warp/Columns;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&3U)||row_count>512||(row_count>32U/Columns&&row_count%(32U/Columns))
            ||!column_count||column_count>16384||first>=row_count*column_count
            ||!query_count||query_count>row_count*column_count-first)return;
    unsigned members=lw_members(row_count,Columns);
    unsigned block=lw_block(first,row_count,column_count,Columns)+blockIdx.x;
    unsigned block_ordinal=lw_first(block,row_count,column_count,Columns);
    if(block_ordinal>=first+query_count)return;
    unsigned col=lw_col_base(block,column_count,Columns),width=(column_count-col<Columns?column_count-col:Columns);
    unsigned block_row=lw_row_base(block,row_count,column_count,Columns);
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
    __shared__ unsigned uniform_cache[Columns][6*128];
    __shared__ unsigned fragments[Columns*Steps*4*32];
    __shared__ unsigned a_stage[ShareA?4*Steps*10*32:1];
    for(unsigned i=threadIdx.x;i<Columns*16U*128U;i+=256U){
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

    for(unsigned chunk=0;chunk<32768;chunk+=Steps*32U){
        // Each column has 8/Columns producers; all four K32 steps are built exactly once.
        unsigned producer_column=warp%Columns;
        #pragma unroll
        for(unsigned producer_step=warp/Columns;producer_step<Steps;producer_step+=8U/Columns){
            unsigned b0=0,b1=0,c0=0,c1=0;
            if(producer_column<width)
                b_transpose6_fragments(uniform_cache[producer_column],pb,chunk+producer_step*32U,lane,b0,b1,c0,c1);
            fragments[pair_depth_b_index(producer_column,producer_step,0U,lane,Steps)]=b0;
            fragments[pair_depth_b_index(producer_column,producer_step,1U,lane,Steps)]=b1;
            fragments[pair_depth_b_index(producer_column,producer_step,2U,lane,Steps)]=c0;
            fragments[pair_depth_b_index(producer_column,producer_step,3U,lane,Steps)]=c1;
        }
        if constexpr(ShareA){
            if(a_loader){
                #pragma unroll 1
                for(unsigned step=0;step<Steps;++step){
                    unsigned off=step*8U;
                    a_stage[a_share_index(quartet,step,0U,lane)]=ap0[off+0U];
                    a_stage[a_share_index(quartet,step,1U,lane)]=ap1[off+0U];
                    a_stage[a_share_index(quartet,step,2U,lane)]=ap0[off+4U];
                    a_stage[a_share_index(quartet,step,3U,lane)]=ap1[off+4U];
                    a_stage[a_share_index(quartet,step,4U,lane)]=ap2[off+0U];
                    a_stage[a_share_index(quartet,step,5U,lane)]=ap3[off+0U];
                    a_stage[a_share_index(quartet,step,6U,lane)]=ap2[off+4U];
                    a_stage[a_share_index(quartet,step,7U,lane)]=ap3[off+4U];
                    a_stage[a_share_index(quartet,step,8U,lane)]=ap4[off+0U];
                    a_stage[a_share_index(quartet,step,9U,lane)]=ap4[off+4U];
                }
            }
        }
        __syncthreads();
        if(live){
            #pragma unroll 1
            for(unsigned step=0;step<Steps;++step){
                unsigned offset=chunk+step*32U;
                unsigned b0=fragments[pair_depth_b_index(column_lane,step,0U,lane,Steps)];
                unsigned b1=fragments[pair_depth_b_index(column_lane,step,1U,lane,Steps)];
                unsigned c0=fragments[pair_depth_b_index(column_lane,step,2U,lane,Steps)];
                unsigned c1=fragments[pair_depth_b_index(column_lane,step,3U,lane,Steps)];
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
        // Every consumer finishes before any producer overwrites the buffer.
        __syncthreads();
        if constexpr(ShareA){
            if(a_loader&&chunk+Steps*32U<32768U){
                ap0+=Steps*8U;ap1+=Steps*8U;ap2+=Steps*8U;ap3+=Steps*8U;ap4+=Steps*8U;
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

extern "C" __global__ void layout_col4_scan(PH_BQ_ARGS){layout_width_body<4>(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}
extern "C" __global__ void layout_col8_scan(PH_BQ_ARGS){layout_width_body<8>(ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first);}
#undef PH_BQ_ARGS
