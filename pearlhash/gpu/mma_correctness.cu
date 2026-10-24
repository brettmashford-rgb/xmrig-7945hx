// ISC license. Independent exact int8 -> int32 tensor-core correctness path.
// PTX fragment mapping authority: NVIDIA PTX ISA, mma.m16n8k32 integer layout.
// https://docs.nvidia.com/cuda/parallel-thread-execution/#warp-level-matrix-fragment-mma-16832
// Inputs are already-noised selected A rows / transposed B columns. No pool IO.
#include "keyed64.h"

__device__ unsigned mma_pack4(const signed char *data,unsigned row,unsigned rows,
                             unsigned k,unsigned offset) {
    if(row>=rows)return 0;
    unsigned packed=0;
    for(unsigned byte=0;byte<4;++byte)
        packed|=(unsigned(data[row*k+offset+byte])&255U)<<(byte*8);
    return packed;
}

extern "C" __global__ void mma_cumulative(const signed char *a,const signed char *bt,
    int *products,unsigned rows,unsigned cols,unsigned k,unsigned rank) {
    if(blockDim.x!=128 || !rows || rows>32 || !cols || cols>32 || !rank ||
       rank%32 || !k || k%rank || k>65536)return;
    unsigned warp=blockIdx.x*4+threadIdx.x/32;
    unsigned col_tiles=(cols+7)/8,total_tiles=((rows+15)/16)*col_tiles;
    if(warp>=total_tiles)return; // warp-uniform exit before any collective MMA
    unsigned lane=threadIdx.x%32,group=lane/4,thread=lane%4;
    unsigned row_base=(warp/col_tiles)*16,col_base=(warp%col_tiles)*8;
    unsigned r0=row_base+group,r1=r0+8,c0=col_base+thread*2,c1=c0+1;
    int d0=0,d1=0,d2=0,d3=0;
    for(unsigned offset=0;offset<k;offset+=32) {
        unsigned a0=mma_pack4(a,r0,rows,k,offset+thread*4);
        unsigned a1=mma_pack4(a,r1,rows,k,offset+thread*4);
        unsigned a2=mma_pack4(a,r0,rows,k,offset+thread*4+16);
        unsigned a3=mma_pack4(a,r1,rows,k,offset+thread*4+16);
        unsigned b0=mma_pack4(bt,col_base+group,cols,k,offset+thread*4);
        unsigned b1=mma_pack4(bt,col_base+group,cols,k,offset+thread*4+16);
        asm volatile(
            "mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 "
            "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
            : "+r"(d0),"+r"(d1),"+r"(d2),"+r"(d3)
            : "r"(a0),"r"(a1),"r"(a2),"r"(a3),"r"(b0),"r"(b1));
        if((offset+32)%rank==0) {
            unsigned step=(offset+32)/rank-1,base=step*rows*cols;
            if(r0<rows&&c0<cols)products[base+r0*cols+c0]=d0;
            if(r0<rows&&c1<cols)products[base+r0*cols+c1]=d1;
            if(r1<rows&&c0<cols)products[base+r1*cols+c0]=d2;
            if(r1<rows&&c1<cols)products[base+r1*cols+c1]=d3;
        }
    }
}

extern "C" __global__ void mma_fold_digest(const int *products,const unsigned *key,
    unsigned *words,unsigned *digest,unsigned pairs,unsigned steps) {
    if(blockIdx.x||threadIdx.x)return;
    for(unsigned i=0;i<16;++i)words[i]=0;
    for(unsigned step=0;step<steps;++step) {
        unsigned folded=0;
        for(unsigned pair=0;pair<pairs;++pair)folded^=unsigned(products[step*pairs+pair]);
        unsigned slot=step%16,old=words[slot];
        words[slot]=((old<<13)|(old>>19))^folded;
    }
    ph::keyed64(words,key,digest);
}
