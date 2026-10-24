// ISC license; see ../LICENSE. Independent observed nonce-tail primitive.
#include "keyed64.h"

extern "C" __global__ void nonce_tail(const unsigned *input, unsigned *output,
                                     unsigned count) {
    unsigned index=blockIdx.x*blockDim.x+threadIdx.x;
    if(index>=count) return;
    const unsigned iv[8]={0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
                          0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    unsigned v[16],m[16]={};
    for(int i=0;i<8;++i) v[i]=iv[i];
    for(int i=0;i<4;++i) { v[8+i]=iv[i]; m[i]=input[index*4+i]; }
    v[12]=0;v[13]=0;v[14]=16;v[15]=11; // unkeyed, START|END|ROOT
    const int permutation[16]={2,6,3,10,7,0,4,13,1,11,12,5,9,14,15,8};
    for(int round=0;round<7;++round) {
        ph::mix(v,0,4,8,12,m[0],m[1]); ph::mix(v,1,5,9,13,m[2],m[3]);
        ph::mix(v,2,6,10,14,m[4],m[5]); ph::mix(v,3,7,11,15,m[6],m[7]);
        ph::mix(v,0,5,10,15,m[8],m[9]); ph::mix(v,1,6,11,12,m[10],m[11]);
        ph::mix(v,2,7,8,13,m[12],m[13]); ph::mix(v,3,4,9,14,m[14],m[15]);
        unsigned next[16];
        for(int i=0;i<16;++i) next[i]=m[permutation[i]];
        for(int i=0;i<16;++i) m[i]=next[i];
    }
    for(int word=0;word<4;++word) {
        unsigned hash=v[word]^v[word+8], packed=0;
        for(int byte=0;byte<4;++byte) {
            unsigned value=(hash>>(8*byte))&255U;
            int signal=int(value%129U)-64;
            packed|=(unsigned(signal)&255U)<<(8*byte);
        }
        output[index*4+word]=packed;
    }
}
