// ISC license; see ../LICENSE. Keyed BLAKE3 full-chunk chaining values.
// Chaining values are commitment-tree leaves, NOT standalone root digests.
#include "keyed64.h"
extern "C" __global__ void keyed_chunk_cvs(const unsigned *input,
    const unsigned *key, unsigned long long first_chunk, unsigned count,
    unsigned *output) {
    unsigned index=blockIdx.x*blockDim.x+threadIdx.x;
    if(index>=count) return;
    unsigned cv[8];
    for(int i=0;i<8;++i) cv[i]=key[i];
    unsigned long long counter=first_chunk+index;
    for(unsigned block=0;block<16;++block) {
        unsigned v[16],m[16];
        for(int i=0;i<8;++i) v[i]=cv[i];
        v[8]=0x6a09e667U;v[9]=0xbb67ae85U;
        v[10]=0x3c6ef372U;v[11]=0xa54ff53aU;
        v[12]=unsigned(counter);v[13]=unsigned(counter>>32);
        v[14]=64;v[15]=16U|(block==0?1U:0U)|(block==15?2U:0U);
        for(int i=0;i<16;++i) m[i]=input[static_cast<unsigned long long>(index)*256+block*16+i];
        const int perm[16]={2,6,3,10,7,0,4,13,1,11,12,5,9,14,15,8};
        for(int round=0;round<7;++round) {
            ph::mix(v,0,4,8,12,m[0],m[1]);ph::mix(v,1,5,9,13,m[2],m[3]);
            ph::mix(v,2,6,10,14,m[4],m[5]);ph::mix(v,3,7,11,15,m[6],m[7]);
            ph::mix(v,0,5,10,15,m[8],m[9]);ph::mix(v,1,6,11,12,m[10],m[11]);
            ph::mix(v,2,7,8,13,m[12],m[13]);ph::mix(v,3,4,9,14,m[14],m[15]);
            unsigned next[16];
            for(int i=0;i<16;++i) next[i]=m[perm[i]];
            for(int i=0;i<16;++i) m[i]=next[i];
        }
        for(int i=0;i<8;++i) cv[i]=v[i]^v[i+8];
    }
    for(int i=0;i<8;++i) output[static_cast<unsigned long long>(index)*8+i]=cv[i];
}
