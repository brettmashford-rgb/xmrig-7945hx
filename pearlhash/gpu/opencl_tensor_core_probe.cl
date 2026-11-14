// ISC. OpenCL C host/kernel probe for NVIDIA's inline-PTX integer MMA path.
// This is a matrix-engine feasibility/throughput probe, not a miner scanner.

inline uint ph_pack4(__global const char *p, uint base) {
    uint x0=(uint)((uchar)p[base+0]);
    uint x1=(uint)((uchar)p[base+1]);
    uint x2=(uint)((uchar)p[base+2]);
    uint x3=(uint)((uchar)p[base+3]);
    return x0|(x1<<8)|(x2<<16)|(x3<<24);
}

inline void ph_mma(uint a0,uint a1,uint a2,uint a3,uint b0,uint b1,
                   __private int *d0,__private int *d1,
                   __private int *d2,__private int *d3) {
    asm volatile(
        "mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 "
        "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
        : "+r"(*d0),"+r"(*d1),"+r"(*d2),"+r"(*d3)
        : "r"(a0),"r"(a1),"r"(a2),"r"(a3),"r"(b0),"r"(b1));
}

// One subgroup computes one 16x8 signed-int8 product. Input arrays contain
// batch matrices: A[batch][16][K] and BT[batch][8][K].
__kernel __attribute__((reqd_work_group_size(128,1,1)))
void pearl_opencl_mma_probe(__global const char *a,
                            __global const char *bt,
                            __global int *out,
                            uint k, uint batch_count) {
    uint lane=(uint)get_local_id(0)&31U;
    uint warp=(uint)get_global_id(0)>>5;
    uint batch=warp%batch_count;
    uint group=lane/4U,thread=lane%4U;
    uint abase=batch*16U*k;
    uint bbase=batch*8U*k;
    uint r0=group,r1=group+8U,c0=thread*2U,c1=c0+1U;
    int d0=0,d1=0,d2=0,d3=0;
    for(uint offset=0;offset<k;offset+=32U) {
        uint a0=ph_pack4(a,abase+r0*k+offset+thread*4U);
        uint a1=ph_pack4(a,abase+r1*k+offset+thread*4U);
        uint a2=ph_pack4(a,abase+r0*k+offset+thread*4U+16U);
        uint a3=ph_pack4(a,abase+r1*k+offset+thread*4U+16U);
        uint b0=ph_pack4(bt,bbase+group*k+offset+thread*4U);
        uint b1=ph_pack4(bt,bbase+group*k+offset+thread*4U+16U);
        ph_mma(a0,a1,a2,a3,b0,b1,&d0,&d1,&d2,&d3);
    }
    uint obase=warp*128U;
    out[obase+r0*8U+c0]=d0;
    out[obase+r0*8U+c1]=d1;
    out[obase+r1*8U+c0]=d2;
    out[obase+r1*8U+c1]=d3;
}
