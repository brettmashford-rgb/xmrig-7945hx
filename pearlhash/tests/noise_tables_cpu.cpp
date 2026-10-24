// ISC. Execute unchanged noise kernel bodies on CPU for differential checks.
// This does not execute the CUDA ISA, MMA, driver, or GPU scheduling.
#define PEARL_NOISE_CPU_CHECK
#define __global__
struct Dim { unsigned x; } blockIdx,blockDim,threadIdx;
#include "../gpu/noise_mma.cu"

extern "C" void check_noise_uniform(const unsigned *indices,const unsigned *key,
    signed char *out,unsigned rows,unsigned rank,unsigned label) {
    blockDim.x=128;
    for(blockIdx.x=0;blockIdx.x<(rows*(rank/32)+127)/128;++blockIdx.x)
        for(threadIdx.x=0;threadIdx.x<128;++threadIdx.x)
            noise_uniform(indices,key,out,rows,rank,label);
}
extern "C" void check_noise_permutation(const unsigned *key,unsigned *out,
    unsigned k,unsigned rank,unsigned label) {
    blockDim.x=128;
    for(blockIdx.x=0;blockIdx.x<(k/8+127)/128;++blockIdx.x)
        for(threadIdx.x=0;threadIdx.x<128;++threadIdx.x)
            noise_permutation(key,out,k,rank,label);
}
extern "C" void check_noise_apply(const signed char *signal,const signed char *uniform,
    const unsigned *pairs,signed char *out,unsigned rows,unsigned k,unsigned rank) {
    blockDim.x=128;
    for(blockIdx.x=0;blockIdx.x<(rows*k+127)/128;++blockIdx.x)
        for(threadIdx.x=0;threadIdx.x<128;++threadIdx.x)
            noise_apply(signal,uniform,pairs,out,rows,k,rank);
}
