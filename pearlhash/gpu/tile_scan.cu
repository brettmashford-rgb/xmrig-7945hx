// ISC. Bounded tile search over materialized signed matrices, no pool IO.
// The same collective/target/queue body is also used by virtual_tile_scan.cu.
#include "noise_mma.cu"
#include "scan_target.h"
#include "tile_scan_core.cuh"

struct MaterializedScanInput {
    const signed char *a,*bt;
    unsigned pool_rows,pool_cols,k;
    __device__ bool valid()const {return pool_rows&&pool_rows<=32&&pool_cols&&pool_cols<=32;}
    __device__ unsigned pack_a(const unsigned *map,unsigned row,unsigned rows,unsigned offset)const {
        return row<rows?mma_pack4(a,map[row],pool_rows,k,offset):0;
    }
    __device__ unsigned pack_b(const unsigned *map,unsigned row,unsigned rows,unsigned offset)const {
        return row<rows?mma_pack4(bt,map[row],pool_cols,k,offset):0;
    }
};

// Descriptor: [rows, cols, A slot[32], B slot[32]], 66 u32 words per tile.
// Candidate: [tile index, generation low/high, digest[8]], 11 u32 words.
extern "C" __global__ void tile_scan(const signed char *a,const signed char *bt,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned pool_rows,unsigned pool_cols,
    unsigned k,unsigned rank,unsigned long long generation) {
    MaterializedScanInput inputs{a,bt,pool_rows,pool_cols,k};
    tile_scan_body(inputs,descriptors,bounds,key,status,candidates,audit_words,audit,
                   capacity,query_count,k,rank,generation);
}
