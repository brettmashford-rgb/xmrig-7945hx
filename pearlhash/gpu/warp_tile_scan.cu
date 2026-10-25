// ISC. One complete query per warp; no cross-warp prefix barriers.
// Include the established kernels so one module can compare both paths.
#include "virtual_tile_scan.cu"

extern "C" __global__ void warp_virtual_tile_scan(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k,
    unsigned rank,int fill,unsigned long long generation) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32;
    unsigned query=blockIdx.x*8+warp;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256 || query>=query_count || !inputs.valid())return;
    const unsigned *desc=descriptors+query*66;
    unsigned rows=desc[0],cols=desc[1];
    if(!rows || rows>32 || !cols || cols>32)return;
    const unsigned *ra=desc+2,*cb=desc+34;
    unsigned col_tiles=(cols+7)/8,tiles=((rows+15)/16)*col_tiles;
    unsigned group=lane/4,thread=lane%4;
    int d[8][4];
    #pragma unroll
    for(unsigned t=0;t<8;++t) {
        #pragma unroll
        for(unsigned j=0;j<4;++j)d[t][j]=0;
    }
    // Transcript slot i belongs to lane i. All lanes retain the prefix fold;
    // no shared transcript or cross-warp communication is needed.
    unsigned word=0;
    for(unsigned offset=0;offset<k;offset+=32) {
        #pragma unroll
        for(unsigned t=0;t<8;++t)if(t<tiles) {
            unsigned r0=(t/col_tiles)*16+group,r1=r0+8;
            unsigned col_base=(t%col_tiles)*8;
            unsigned a0=inputs.pack_a(ra,r0,rows,offset+thread*4);
            unsigned a1=inputs.pack_a(ra,r1,rows,offset+thread*4);
            unsigned a2=inputs.pack_a(ra,r0,rows,offset+thread*4+16);
            unsigned a3=inputs.pack_a(ra,r1,rows,offset+thread*4+16);
            unsigned b0=inputs.pack_b(cb,col_base+group,cols,offset+thread*4);
            unsigned b1=inputs.pack_b(cb,col_base+group,cols,offset+thread*4+16);
            mma_accumulate(a0,a1,a2,a3,b0,b1,d[t][0],d[t][1],d[t][2],d[t][3]);
        }
        if((offset+32)%rank==0) {
            unsigned folded=0;
            #pragma unroll
            for(unsigned t=0;t<8;++t)if(t<tiles) {
                unsigned r0=(t/col_tiles)*16+group,r1=r0+8;
                unsigned c0=(t%col_tiles)*8+thread*2,c1=c0+1;
                if(r0<rows&&c0<cols)folded^=unsigned(d[t][0]);
                if(r0<rows&&c1<cols)folded^=unsigned(d[t][1]);
                if(r1<rows&&c0<cols)folded^=unsigned(d[t][2]);
                if(r1<rows&&c1<cols)folded^=unsigned(d[t][3]);
            }
            for(unsigned delta=16;delta;delta>>=1)
                folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
            unsigned slot=((offset+32)/rank-1)%16;
            if(lane==slot)word=((word<<13)|(word>>19))^folded;
        }
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
