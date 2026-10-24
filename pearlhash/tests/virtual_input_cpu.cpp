// ISC. Actual uniform kernel body and fragment loader on CPU; no GPU ISA/scheduling.
#define PEARL_VIRTUAL_CPU_CHECK
#define __global__
struct Dim {unsigned x;} blockIdx,blockDim,threadIdx;
#include "../gpu/virtual_tile_scan.cu"

extern "C" void check_uniform_range(const unsigned *key,signed char *out,
    unsigned first,unsigned count,unsigned label) {
    blockDim.x=128;
    for(blockIdx.x=0;blockIdx.x<(count+127)/128;++blockIdx.x)
        for(threadIdx.x=0;threadIdx.x<128;++threadIdx.x)
            noise_uniform_range(key,out,first,count,label);
}

extern "C" unsigned check_virtual_pack(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,
    unsigned m,unsigned n,unsigned k,unsigned rank,int fill,unsigned side,
    const unsigned *map,unsigned row,unsigned rows,unsigned offset) {
    VirtualScanInput input{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(!input.valid())return 0;
    return input.pack(side!=0,map,row,rows,offset);
}
