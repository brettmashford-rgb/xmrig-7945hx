// ISC. Preserve all established scanners and add a same-stream guard collector.
#include "direct_resident_scan.cu"
#include "guard_snapshot.h"
extern "C" __global__ void resident_guard_snapshot(const unsigned long long *addresses,
    const unsigned char *status,unsigned char *output,unsigned guards,
    unsigned long long generation,unsigned first,unsigned count) {
    if(blockDim.x!=128||!guards||guards>64||!count||count>4096)return;
    unsigned i=blockIdx.x*128+threadIdx.x;
    if(i<24+guards*16)output[i]=pearl_snapshot_byte(addresses,status,generation,first,count,i);
}
