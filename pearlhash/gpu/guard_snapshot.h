// ISC. Byte-exact status, window identity and guard gathering; no scan math.
#pragma once
#ifdef __CUDACC__
#define PH_SNAPSHOT_HD __host__ __device__
#else
#define PH_SNAPSHOT_HD
#endif
PH_SNAPSHOT_HD inline unsigned char pearl_snapshot_byte(const unsigned long long *addresses,
    const unsigned char *status,unsigned long long generation,unsigned first,unsigned count,unsigned i) {
    if(i<8)return status[i];
    if(i<16)return (generation>>((i-8)*8))&255;
    if(i<20)return (first>>((i-16)*8))&255;
    if(i<24)return (count>>((i-20)*8))&255;
    unsigned offset=i-24;
    return reinterpret_cast<const unsigned char*>(addresses[offset/16])[offset%16];
}
#undef PH_SNAPSHOT_HD
