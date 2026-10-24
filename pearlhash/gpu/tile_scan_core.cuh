// ISC. Shared exact MMA/fold/target/queue body for materialized and virtual inputs.
// Parent includes mma_correctness.cu and scan_target.h before this header.
#pragma once

template<class Inputs>
__device__ __forceinline__ void tile_scan_body(const Inputs &inputs,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned k,unsigned rank,
    unsigned long long generation) {
    if(blockDim.x!=256 || blockIdx.x>=query_count || !inputs.valid() ||
       !rank || rank%32 || !k || k%rank || k>65536)return;
    const unsigned *desc=descriptors+blockIdx.x*66;
    unsigned rows=desc[0],cols=desc[1];
    if(!rows || rows>32 || !cols || cols>32)return; // block-uniform
    const unsigned *ra=desc+2,*cb=desc+34;
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32,group=lane/4,thread=lane%4;
    unsigned col_tiles=(cols+7)/8,tiles=((rows+15)/16)*col_tiles;
    bool active=warp<tiles; // All eight warps still join every block barrier.
    unsigned r0=(warp/col_tiles)*16+group,r1=r0+8;
    unsigned col_base=(warp%col_tiles)*8,c0=col_base+thread*2,c1=c0+1;
    __shared__ unsigned words[16],warp_folds[8];
    if(threadIdx.x<16)words[threadIdx.x]=0;
    __syncthreads();
    int d0=0,d1=0,d2=0,d3=0;
    for(unsigned offset=0;offset<k;offset+=32) {
        if(active) {
            unsigned a0=inputs.pack_a(ra,r0,rows,offset+thread*4);
            unsigned a1=inputs.pack_a(ra,r1,rows,offset+thread*4);
            unsigned a2=inputs.pack_a(ra,r0,rows,offset+thread*4+16);
            unsigned a3=inputs.pack_a(ra,r1,rows,offset+thread*4+16);
            unsigned b0=inputs.pack_b(cb,col_base+group,cols,offset+thread*4);
            unsigned b1=inputs.pack_b(cb,col_base+group,cols,offset+thread*4+16);
            mma_accumulate(a0,a1,a2,a3,b0,b1,d0,d1,d2,d3);
        }
        if((offset+32)%rank==0) {
            unsigned folded=0;
            if(active) {
                if(r0<rows&&c0<cols)folded^=unsigned(d0);
                if(r0<rows&&c1<cols)folded^=unsigned(d1);
                if(r1<rows&&c0<cols)folded^=unsigned(d2);
                if(r1<rows&&c1<cols)folded^=unsigned(d3);
            }
            // All lanes participate, including inactive/padded zero contributors.
            for(unsigned delta=16;delta;delta>>=1)
                folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
            if(!lane)warp_folds[warp]=folded;
            __syncthreads();
            if(!threadIdx.x) {
                unsigned value=0;
                for(unsigned i=0;i<8;++i)value^=warp_folds[i];
                unsigned slot=((offset+32)/rank-1)%16,old=words[slot];
                words[slot]=((old<<13)|(old>>19))^value;
            }
            __syncthreads(); // Prevent next prefix's writers racing this fold.
        }
    }
    if(threadIdx.x)return;
    unsigned digest[8];ph::keyed64(words,key,digest);
    if(audit)for(unsigned i=0;i<16;++i)audit_words[blockIdx.x*16+i]=words[i];
    if(!ph::digest_meets_bound(digest,bounds+blockIdx.x*8))return;
    unsigned slot=atomicAdd(status,1U);
    if(slot>=capacity) {atomicExch(status+1,1U);return;}
    unsigned *out=candidates+slot*11;
    out[0]=blockIdx.x;out[1]=unsigned(generation);out[2]=unsigned(generation>>32);
    for(unsigned i=0;i<8;++i)out[3+i]=digest[i];
}
