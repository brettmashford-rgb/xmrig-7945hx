// ISC. Independent 2x8 search-tile block; shared K128 inputs, two cp.async stages.
#include "fragment_cached_tile_scan.cu"

__device__ __forceinline__ void cooperative_prefetch(unsigned *stage,
    const signed char *a,const signed char *b,const unsigned *descriptors,
    unsigned rows_a,unsigned rows_b,unsigned offset) {
    for(unsigned i=threadIdx.x;i<8*148;i+=256) {
        unsigned fragment=i/148,row=i%148;
        unsigned index,rows;const signed char *source;
        if(row<20) {
            index=descriptors[(row/10)*8*66+2+row%10];rows=rows_a;source=a;
        } else {
            unsigned br=row-20;
            index=descriptors[(br/16)*66+34+br%16];rows=rows_b;source=b;
        }
        const unsigned *input=reinterpret_cast<const unsigned *>(source)+
            fragment_word_index(rows,index,offset+fragment*16);
        unsigned address=static_cast<unsigned>(__cvta_generic_to_shared(stage+i*4));
        asm volatile("cp.async.ca.shared.global [%0], [%1], 16;\n"::"r"(address),"l"(input));
    }
    asm volatile("cp.async.commit_group;\n"::);
}

__device__ __forceinline__ unsigned cooperative_pack(const unsigned *stage,
    unsigned row,unsigned offset,bool live=true) {
    return live?stage[(offset/16)*148*4+row*4+(offset%16)/4]:0U;
}

extern "C" __global__ void cooperative_tile_scan(const signed char *a,const signed char *b,
    const unsigned *unused_a,const unsigned *unused_b,const signed char *unused_tail,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k,
    unsigned rank,int fill,unsigned long long generation) {
    if(blockDim.x!=256||query_count%16||blockIdx.x>=query_count/16||!m||!n||
       k!=32768||rank!=128||fill!=64)return;
    const unsigned *block_desc=descriptors+blockIdx.x*16*66;
    unsigned local_query=threadIdx.x/16,item=threadIdx.x%16;
    const unsigned *desc=block_desc+local_query*66;
    unsigned ag=local_query/8,bg=local_query%8;
    bool invalid=desc[0]!=10||desc[1]!=16||desc[34+item]>=n||
        desc[34+item]!=block_desc[bg*66+34+item];
    if(item<10)invalid|=desc[2+item]>=m||desc[2+item]!=block_desc[ag*8*66+2+item];
    if(__syncthreads_or(invalid))return;
    __shared__ __align__(16) unsigned stages[2][8*148*4];
    cooperative_prefetch(stages[0],a,b,block_desc,m,n,0);
    cooperative_prefetch(stages[1],a,b,block_desc,m,n,128);
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    unsigned group=lane/4,thread=lane%4,group_a=warp/4,pair_b=(warp%4)*2;
    int d[4][4];
    #pragma unroll
    for(unsigned col=0;col<4;++col) {
        #pragma unroll
        for(unsigned i=0;i<4;++i)d[col][i]=0;
    }
    unsigned words_owned[2]={0,0};
    for(unsigned step=0;step<256;++step) {
        if(step<255)asm volatile("cp.async.wait_group 1;\n"::);
        else asm volatile("cp.async.wait_group 0;\n"::);
        __syncthreads();
        const unsigned *stage=stages[step%2];
        #pragma unroll
        for(unsigned offset=0;offset<128;offset+=32) {
            unsigned row0=group_a*10+group,row1=group_a*10+8+group;
            unsigned a0=cooperative_pack(stage,row0,offset+thread*4);
            unsigned a1=cooperative_pack(stage,row1,offset+thread*4,group<2);
            unsigned a2=cooperative_pack(stage,row0,offset+thread*4+16);
            unsigned a3=cooperative_pack(stage,row1,offset+thread*4+16,group<2);
            #pragma unroll
            for(unsigned col=0;col<4;++col) {
                unsigned row=20+pair_b*16+col*8+group;
                unsigned b0=cooperative_pack(stage,row,offset+thread*4);
                unsigned b1=cooperative_pack(stage,row,offset+thread*4+16);
                mma_accumulate(a0,a1,a2,a3,b0,b1,d[col][0],d[col][1],d[col][2],d[col][3]);
            }
        }
        #pragma unroll
        for(unsigned tile=0;tile<2;++tile) {
            unsigned folded=unsigned(d[tile*2][0])^unsigned(d[tile*2][1])^
                            unsigned(d[tile*2+1][0])^unsigned(d[tile*2+1][1]);
            if(group<2)folded^=unsigned(d[tile*2][2])^unsigned(d[tile*2][3])^
                              unsigned(d[tile*2+1][2])^unsigned(d[tile*2+1][3]);
            for(unsigned delta=16;delta;delta>>=1)folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
            if(lane==step%16)words_owned[tile]=((words_owned[tile]<<13)|(words_owned[tile]>>19))^folded;
        }
        __syncthreads();
        if(step+2<256)cooperative_prefetch(stages[step%2],a,b,block_desc,m,n,(step+2)*128);
    }
    #pragma unroll
    for(unsigned tile=0;tile<2;++tile) {
        unsigned words[16];
        #pragma unroll
        for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,words_owned[tile],i);
        if(!lane) {
            unsigned query=blockIdx.x*16+group_a*8+pair_b+tile,digest[8];
            ph::keyed64(words,key,digest);
            if(audit)for(unsigned i=0;i<16;++i)audit_words[query*16+i]=words[i];
            if(ph::digest_meets_bound(digest,bounds+query*8)) {
                unsigned slot=atomicAdd(status,1U);
                if(slot>=capacity)atomicExch(status+1,1U);
                else {
                    unsigned *out=candidates+slot*11;
                    out[0]=query;out[1]=unsigned(generation);out[2]=unsigned(generation>>32);
                    for(unsigned i=0;i<8;++i)out[3+i]=digest[i];
                }
            }
        }
    }
}
