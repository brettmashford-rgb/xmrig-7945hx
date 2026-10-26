// ISC. Production noise is [-32,31]; biased cache bytes are [0,63].
#pragma once
#ifdef __CUDACC__
#define PH_BB_HD __host__ __device__
#else
#define PH_BB_HD
#endif
PH_BB_HD inline unsigned b_bias_byte(int value) {return unsigned(value+32);}
PH_BB_HD inline unsigned b_bias_difference(unsigned a,unsigned b) {
    // Each byte is 64+a-b in [1,127]: no cross-byte borrow or carry.
    return (a|0x40404040U)-b;
}
PH_BB_HD inline unsigned b_bias_value(const unsigned *cache,unsigned pair,unsigned block) {
    return b_bias_difference(cache[(pair&65535U)*5+block],cache[(pair>>16)*5+block]);
}
#undef PH_BB_HD
