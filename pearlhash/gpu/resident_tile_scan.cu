// ISC. Reuse validated tile math; descriptors are generated on device.
#include "cached_a_tile_scan.cu"
#include "resident_descriptors.h"
extern "C" __global__ void resident_query_descriptors(const unsigned *rows,const unsigned *cols,
    unsigned row_count,unsigned column_count,unsigned first,unsigned count,unsigned *descriptors) {
    if(!row_count||row_count>512||!column_count||column_count>16384||!count||count>4096
            ||first>=row_count*column_count||count>row_count*column_count-first)return;
    unsigned index=blockIdx.x*blockDim.x+threadIdx.x;
    if(index<count*66)descriptors[index]=resident_descriptor_word(rows,cols,column_count,first+index/66,index%66);
}
