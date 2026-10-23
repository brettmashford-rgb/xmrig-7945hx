// ISC license; see ../LICENSE. Independent fixed-length keyed BLAKE3.
// ONLY 64-byte inputs, 32-byte keys and 32-byte root output are supported.
#pragma once
#ifdef __CUDACC__
#define PH_HD __host__ __device__
#else
#define PH_HD
#endif
namespace ph {
using Word = unsigned;
static_assert(sizeof(Word)==4);
PH_HD inline Word ror(Word x, Word n) { return (x>>n)|(x<<(32-n)); }
PH_HD inline void mix(Word *v, int a, int b, int c, int d, Word x, Word y) {
    v[a]+=v[b]+x; v[d]=ror(v[d]^v[a],16);
    v[c]+=v[d]; v[b]=ror(v[b]^v[c],12);
    v[a]+=v[b]+y; v[d]=ror(v[d]^v[a],8);
    v[c]+=v[d]; v[b]=ror(v[b]^v[c],7);
}
PH_HD inline void keyed64(const Word *message, const Word *key, Word *out) {
    Word v[16], m[16];
    for (int i=0;i<8;++i) v[i]=key[i];
    v[8]=0x6a09e667U; v[9]=0xbb67ae85U; v[10]=0x3c6ef372U; v[11]=0xa54ff53aU;
    v[12]=0; v[13]=0; v[14]=64;
    v[15]=27; // KEYED_HASH | CHUNK_START | CHUNK_END | ROOT
    for (int i=0;i<16;++i) m[i]=message[i];
    const int perm[16]={2,6,3,10,7,0,4,13,1,11,12,5,9,14,15,8};
    for(int round=0;round<7;++round) {
        mix(v,0,4,8,12,m[0],m[1]); mix(v,1,5,9,13,m[2],m[3]);
        mix(v,2,6,10,14,m[4],m[5]); mix(v,3,7,11,15,m[6],m[7]);
        mix(v,0,5,10,15,m[8],m[9]); mix(v,1,6,11,12,m[10],m[11]);
        mix(v,2,7,8,13,m[12],m[13]); mix(v,3,4,9,14,m[14],m[15]);
        Word next[16];
        for(int i=0;i<16;++i) next[i]=m[perm[i]];
        for(int i=0;i<16;++i) m[i]=next[i];
    }
    for(int i=0;i<8;++i) out[i]=v[i]^v[i+8];
}
PH_HD inline void random_hash(Word block, Word label, const Word *key, Word slot, Word *out) {
    Word message[16]={};
    message[slot]=block+1;
    message[8]=label; message[9]=0x726f736eU; // padded "A_tensor" or "B_tensor"
    keyed64(message,key,out);
}
PH_HD inline int uniform(Word row, Word rank, Word col, Word label, const Word *key) {
    Word index=row*rank+col, hash[8];
    random_hash(index/32,label,key,0,hash);
    Word byte=(hash[(index%32)/4]>>(8*(index%4)))&255;
    return int(byte&63)-32;
}
PH_HD inline int noise(Word row, Word l, Word rank, Word label, const Word *key) {
    Word hash[8]; random_hash(l/8,label,key,1,hash);
    Word value=hash[l%8], first=value&(rank-1);
    Word second=first^(1+Word((static_cast<unsigned long long>(rank-1)*value)>>32));
    return uniform(row,rank,first,label,key)-uniform(row,rank,second,label,key);
}
}
#undef PH_HD
