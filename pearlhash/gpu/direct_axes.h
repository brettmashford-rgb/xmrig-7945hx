// ISC. Row-major canonical axis offsets shared by host and CUDA checks.
#pragma once
#ifdef __CUDACC__
#define PH_AXES_HD __host__ __device__
#else
#define PH_AXES_HD
#endif
struct ResidentAxisOffsets { unsigned row,col; };
PH_AXES_HD inline ResidentAxisOffsets resident_axis_offsets(unsigned first,unsigned query,unsigned columns) {
    unsigned tile=first+query;
    return {tile/columns,tile%columns};
}
#undef PH_AXES_HD
