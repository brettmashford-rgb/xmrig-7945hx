// ISC. A caller supplies an already-scaled bound, little-endian 8 x u32.
// This primitive does not infer pool difficulty/configuration/rank scaling.
#pragma once
#ifdef __CUDACC__
#define PH_SCAN_HD __host__ __device__
#else
#define PH_SCAN_HD
#endif
namespace ph {
PH_SCAN_HD inline bool digest_meets_bound(const unsigned *digest,const unsigned *bound) {
    for(int i=7;i>=0;--i) {
        if(digest[i]<bound[i])return true;
        if(digest[i]>bound[i])return false;
    }
    return true; // Equality is accepted, matching the pinned verifier's rule.
}
}
#undef PH_SCAN_HD
