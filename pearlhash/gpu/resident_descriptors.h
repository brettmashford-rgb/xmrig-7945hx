// ISC. Descriptor word mapping shared by CUDA and independent host tests.
#pragma once
#ifdef __CUDACC__
#define PH_RESIDENT_HD __host__ __device__
#else
#define PH_RESIDENT_HD
#endif
PH_RESIDENT_HD inline unsigned resident_descriptor_word(const unsigned *rows,const unsigned *cols,
    unsigned column_count,unsigned tile,unsigned word) {
    if(word==0)return 10;
    if(word==1)return 16;
    return word<34?rows[(tile/column_count)*32+word-2]:cols[(tile%column_count)*32+word-34];
}
#undef PH_RESIDENT_HD
