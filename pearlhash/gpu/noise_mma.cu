// ISC license. Factor deterministic noise into reusable uniform/permutation tables.
// Already-derived seeds and selected signal rows are supplied by the caller.
// No pool IO, seed derivation, matrix commitments or mining search is performed.
#ifdef PEARL_NOISE_CPU_CHECK
#include "keyed64.h"
#else
#include "mma_correctness.cu"
#endif

// One hash produces 32 adjacent uniform bytes. Selected indices may repeat.
extern "C" __global__ void noise_uniform(const unsigned *indices,
    const unsigned *key, signed char *uniform, unsigned rows, unsigned rank,
    unsigned label) {
    unsigned block=blockIdx.x*blockDim.x+threadIdx.x;
    unsigned per_row=rank/32;
    if(!per_row || block>=rows*per_row)return;
    unsigned row=block/per_row,within=block%per_row,hash[8];
    ph::random_hash(indices[row]*per_row+within,label,key,0,hash);
    for(unsigned byte=0;byte<32;++byte)
        uniform[block*32+byte]=int((hash[byte/4]>>(8*(byte%4)))&63U)-32;
}

// Permutation is shared by ALL selected rows of one side, independent of index.
// Store the two rank indices in the low/high 16 bits of each u32.
extern "C" __global__ void noise_permutation(const unsigned *key,unsigned *pairs,
    unsigned k,unsigned rank,unsigned label) {
    unsigned block=blockIdx.x*blockDim.x+threadIdx.x;
    if(block>=k/8)return;
    unsigned hash[8];ph::random_hash(block,label,key,1,hash);
    for(unsigned i=0;i<8;++i) {
        unsigned value=hash[i],first=value&(rank-1);
        unsigned second=first^(1+unsigned((static_cast<unsigned long long>(rank-1)*value)>>32));
        pairs[block*8+i]=first|(second<<16);
    }
}

extern "C" __global__ void noise_apply(const signed char *signal,
    const signed char *uniform,const unsigned *pairs,signed char *noised,
    unsigned rows,unsigned k,unsigned rank) {
    unsigned p=blockIdx.x*blockDim.x+threadIdx.x;
    if(p>=rows*k)return;
    unsigned pair=pairs[p%k],row=p/k;
    int noise=int(uniform[row*rank+(pair&65535)])-int(uniform[row*rank+(pair>>16)]);
    // Host validates signals in [-64,64], noise in [-63,63]: exact int8 range.
    noised[p]=int(signal[p])+noise;
}
