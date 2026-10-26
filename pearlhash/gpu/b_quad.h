// ISC. Four independent modulo-256 B noise values in one unsigned word.
#pragma once
#ifdef __CUDACC__
#define PH_BQ_HD __host__ __device__
#else
#define PH_BQ_HD
#endif
PH_BQ_HD inline unsigned b_quad_difference(unsigned a,unsigned b) {
    // High bits prevent borrow across byte boundaries. Restore each byte's
    // high bit, then add fill=64 without carry crossing into adjacent bytes.
    unsigned difference=((a|0x80808080U)-(b&0x7f7f7f7fU))^((a^~b)&0x80808080U);
    return ((difference&0x7f7f7f7fU)+0x40404040U)^(difference&0x80808080U);
}
PH_BQ_HD inline unsigned b_quad_value(const unsigned *cache,unsigned stride,unsigned pair,unsigned block) {
    return b_quad_difference(cache[(pair&65535U)*stride+block],cache[(pair>>16)*stride+block]);
}
PH_BQ_HD inline unsigned b_quad_source(unsigned group,unsigned thread,unsigned byte) {
    return (group/4)*16+thread*4+byte;
}
PH_BQ_HD inline unsigned b_quad_pick(unsigned value,unsigned group,unsigned byte) {
    return ((value>>((group&3)*8))&255U)<<(byte*8);
}
#undef PH_BQ_HD
