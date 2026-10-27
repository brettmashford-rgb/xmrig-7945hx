// ISC. Single-instruction warp XOR reduction; otherwise identical v060 pair scan.
#include "shared_b_scan.cu"

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first

__device__ __forceinline__ void redux_b_fold(int d0,int d1,int d2,int d3,int e0,int e1,int e2,int e3,
        unsigned group,unsigned lane,unsigned slot,unsigned &word) {
    unsigned folded=unsigned(d0)^unsigned(d1)^unsigned(e0)^unsigned(e1);
    if(group<2)folded^=unsigned(d2)^unsigned(d3)^unsigned(e2)^unsigned(e3);
    asm volatile("redux.sync.xor.b32 %0, %1, 0xffffffff;" : "=r"(folded) : "r"(folded));
    if(lane==slot)word=((word<<13)|(word>>19))^folded;
}
extern "C" __global__ void shared_b_redux_scan(PH_BQ_ARGS) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    if(!row_count||(row_count&1U)||row_count>512||!column_count||column_count>16384
            ||first>=row_count*column_count||query_count>row_count*column_count-first)return;
    unsigned ordinal=(first&~1U)+(blockIdx.x*8+warp)*2;
    if(ordinal>=first+query_count)return;
    unsigned row=shared_b_row(ordinal,column_count),col=shared_b_column(ordinal,column_count);
    const unsigned *ra=row_axes+row*32,*rb=ra+32,*cb=column_axes+col*32;
    bool active0=ordinal>=first,active1=ordinal+1<first+query_count;
    bool invalid=lane<10?(ra[lane]>=m||rb[lane]>=m):(lane<26?cb[lane-10]>=n:false);
    if(__any_sync(0xffffffffU,invalid))return;
    __shared__ unsigned uniform_cache[8][6*128];
    unsigned *cache=uniform_cache[warp];
    for(unsigned i=lane;i<16*128;i+=32) {
        unsigned r=i/128,index=i%128;
        reinterpret_cast<unsigned char*>(cache)[index*6*4+r]=static_cast<unsigned char>(ub[cb[r]*128+index]);
    }
    __syncwarp(0xffffffffU);
    int d0=0,d1=0,d2=0,d3=0,e0=0,e1=0,e2=0,e3=0;
    int f0=0,f1=0,f2=0,f3=0,g0=0,g1=0,g2=0,g3=0;
    unsigned word0=0,word1=0,group=lane/4;
    for(unsigned offset=0;offset<32768;offset+=32) {
        unsigned b0,b1,c0,c1;
        b_transpose6_fragments(cache,pb,offset,lane,b0,b1,c0,c1);
        if(active0)shared_b_a_mma(ua,ra,offset,lane,b0,b1,c0,c1,d0,d1,d2,d3,e0,e1,e2,e3);
        if(active1)shared_b_a_mma(ua,rb,offset,lane,b0,b1,c0,c1,f0,f1,f2,f3,g0,g1,g2,g3);
        if((offset+32)%128==0) {
            unsigned slot=((offset+32)/128-1)%16;
            if(active0)redux_b_fold(d0,d1,d2,d3,e0,e1,e2,e3,group,lane,slot,word0);
            if(active1)redux_b_fold(f0,f1,f2,f3,g0,g1,g2,g3,group,lane,slot,word1);
        }
    }
    unsigned words0[16],words1[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i) {
        if(active0)words0[i]=__shfl_sync(0xffffffffU,word0,i);
        if(active1)words1[i]=__shfl_sync(0xffffffffU,word1,i);
    }
    if(lane)return;
    if(active0)shared_b_emit(words0,key,bounds,status,candidates,audit_words,audit,capacity,ordinal-first,generation);
    if(active1)shared_b_emit(words1,key,bounds,status,candidates,audit_words,audit,capacity,ordinal+1-first,generation);
}

#undef PH_BQ_ARGS
