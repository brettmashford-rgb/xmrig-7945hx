// ISC. K-major 16-byte fragments: neighbouring rows occupy neighbouring words.
#pragma once
#ifdef __CUDACC__
#define PH_FRAGMENT __host__ __device__ __forceinline__
#else
#define PH_FRAGMENT inline
#endif
PH_FRAGMENT unsigned fragment_word_index(unsigned rows,unsigned row,unsigned offset) {
    return (offset/16)*rows*4+row*4+(offset%16)/4;
}
#undef PH_FRAGMENT
