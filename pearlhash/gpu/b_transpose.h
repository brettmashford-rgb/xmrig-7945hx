// ISC. Register transpose: exchange K-byte lane bits with row-byte positions.
#pragma once
#ifdef __CUDACC__
#define PH_BT_HD __host__ __device__
#else
#define PH_BT_HD
#endif
PH_BT_HD inline unsigned b_transpose_index(unsigned lane) {
    return (lane&3U)*4U+((lane>>2)&3U);
}
PH_BT_HD inline unsigned b_transpose_selector(unsigned lane,unsigned stage) {
    return stage==0?((lane&4U)?0x3715U:0x6240U):((lane&8U)?0x3276U:0x5410U);
}
#undef PH_BT_HD
