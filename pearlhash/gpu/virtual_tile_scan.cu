// ISC. Full uniform/permutation cache; virtual noised bytes feed exact MMA.
#ifdef PEARL_VIRTUAL_CPU_CHECK
#include "keyed64.h"
#else
#include "tile_scan.cu"
#endif
#include "virtual_input.h"

// Uniform blocks are 32 adjacent bytes, addressed by global linear noise index.
// The selected u32 noise-index domain permits block counters 0..2^27-1.
extern "C" __global__ void noise_uniform_range(const unsigned *key,signed char *out,
    unsigned first,unsigned count,unsigned label) {
    unsigned p=blockIdx.x*blockDim.x+threadIdx.x;
    if(p>=count || static_cast<unsigned long long>(first)+count>(1ULL<<27))return;
    unsigned hash[8];ph::random_hash(first+p,label,key,0,hash);
    for(unsigned byte=0;byte<32;++byte)
        out[p*32+byte]=int((hash[byte/4]>>(8*(byte%4)))&63U)-32;
}

#ifndef PEARL_VIRTUAL_CPU_CHECK
extern "C" __global__ void virtual_tile_scan(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k,
    unsigned rank,int fill,unsigned long long generation) {
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    tile_scan_body(inputs,descriptors,bounds,key,status,candidates,audit_words,audit,
                   capacity,query_count,k,rank,generation);
}

// Correctness-only probes: (side 0/1, global row, aligned k offset) -> four bytes.
// The actual scan does not allocate or write noised matrices/probe arrays.
extern "C" __global__ void virtual_probe(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,
    const unsigned *requests,unsigned *out,unsigned count,unsigned m,unsigned n,
    unsigned k,unsigned rank,int fill) {
    unsigned p=blockIdx.x*blockDim.x+threadIdx.x;
    if(p>=count)return;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    unsigned side=requests[p*3],row=requests[p*3+1],offset=requests[p*3+2];
    out[p]=inputs.pack(side!=0,&row,0,1,offset);
}
#endif
