#!/usr/bin/env python3
"""NVIDIA OpenCL inline-PTX MMA correctness and throughput probe; never connects to a pool."""
import argparse
import ctypes as C
import json
import random
import time
from pathlib import Path

cl_int=C.c_int32; cl_uint=C.c_uint32; cl_ulong=C.c_uint64
cl_platform=C.c_void_p; cl_device=C.c_void_p; cl_context=C.c_void_p
cl_queue=C.c_void_p; cl_program=C.c_void_p; cl_kernel=C.c_void_p; cl_mem=C.c_void_p; cl_event=C.c_void_p
GPU=1<<2; MEM_READ_ONLY=1<<2; MEM_WRITE_ONLY=1<<1; MEM_COPY_HOST_PTR=1<<5
DEVICE_NAME=0x102B; DEVICE_VERSION=0x102F; DRIVER_VERSION=0x102D
PLATFORM_NAME=0x0902; BUILD_LOG=0x1183

def api(lib,name,restype,args):
    f=getattr(lib,name);f.restype=restype;f.argtypes=args;return f

def info_string(fn,obj,param):
    n=cl_size= C.c_size_t()
    fn(obj,param,0,None,C.byref(n));buf=C.create_string_buffer(n.value)
    fn(obj,param,n.value,buf,None);return buf.value.decode(errors='replace')

def check(code,where):
    if code!=0:raise RuntimeError(f'{where} OpenCL error {code}')

def make_data(k,batches,seed):
    rng=random.Random(seed)
    return bytes((rng.randrange(-2,3)&255 for _ in range(batches*16*k))),bytes((rng.randrange(-2,3)&255 for _ in range(batches*8*k)))

def cpu_reference(a,bt,k):
    # Tiny exact reference; values are signed bytes and results accumulate modulo int32.
    signed=lambda x:x if x<128 else x-256
    out=[]
    for r in range(16):
        for c in range(8):
            acc=0
            for q in range(k):acc+=signed(a[r*k+q])*signed(bt[c*k+q])
            out.append(C.c_int32(acc).value)
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--kernel',default=str(Path(__file__).resolve().parents[1]/'gpu/opencl_tensor_core_probe.cl'))
    p.add_argument('--k',type=int,default=32768);p.add_argument('--warps',type=int,default=512)
    p.add_argument('--batches',type=int,default=8);p.add_argument('--rounds',type=int,default=7)
    args=p.parse_args()
    if args.k<32 or args.k%32 or args.k>32768:raise ValueError('K must be a multiple of 32 in [32,32768]')
    if args.warps<4 or args.warps%4 or args.batches<1 or args.rounds<3:raise ValueError('invalid probe dimensions')
    lib=C.CDLL('libOpenCL.so.1')
    get_platforms=api(lib,'clGetPlatformIDs',cl_int,[cl_uint,C.POINTER(cl_platform),C.POINTER(cl_uint)])
    get_devices=api(lib,'clGetDeviceIDs',cl_int,[cl_platform,cl_ulong,cl_uint,C.POINTER(cl_device),C.POINTER(cl_uint)])
    get_pinfo=api(lib,'clGetPlatformInfo',cl_int,[cl_platform,cl_uint,C.c_size_t,C.c_void_p,C.POINTER(C.c_size_t)])
    get_dinfo=api(lib,'clGetDeviceInfo',cl_int,[cl_device,cl_uint,C.c_size_t,C.c_void_p,C.POINTER(C.c_size_t)])
    create_context=api(lib,'clCreateContext',cl_context,[C.c_void_p,cl_uint,C.POINTER(cl_device),C.c_void_p,C.c_void_p,C.POINTER(cl_int)])
    create_queue=api(lib,'clCreateCommandQueue',cl_queue,[cl_context,cl_device,cl_ulong,C.POINTER(cl_int)])
    create_program=api(lib,'clCreateProgramWithSource',cl_program,[cl_context,cl_uint,C.POINTER(C.c_char_p),C.POINTER(C.c_size_t),C.POINTER(cl_int)])
    build=api(lib,'clBuildProgram',cl_int,[cl_program,cl_uint,C.POINTER(cl_device),C.c_char_p,C.c_void_p,C.c_void_p])
    get_build=api(lib,'clGetProgramBuildInfo',cl_int,[cl_program,cl_device,cl_uint,C.c_size_t,C.c_void_p,C.POINTER(C.c_size_t)])
    create_kernel=api(lib,'clCreateKernel',cl_kernel,[cl_program,C.c_char_p,C.POINTER(cl_int)])
    create_buffer=api(lib,'clCreateBuffer',cl_mem,[cl_context,cl_ulong,C.c_size_t,C.c_void_p,C.POINTER(cl_int)])
    set_arg=api(lib,'clSetKernelArg',cl_int,[cl_kernel,cl_uint,C.c_size_t,C.c_void_p])
    enqueue=api(lib,'clEnqueueNDRangeKernel',cl_int,[cl_queue,cl_kernel,cl_uint,C.POINTER(cl_size),C.POINTER(cl_size),C.POINTER(cl_size),cl_uint,C.c_void_p,C.c_void_p])
    finish=api(lib,'clFinish',cl_int,[cl_queue])
    read=api(lib,'clEnqueueReadBuffer',cl_int,[cl_queue,cl_mem,cl_uint,C.c_size_t,C.c_size_t,C.c_void_p,cl_uint,C.c_void_p,C.c_void_p])
    release=[]
    for name in ('clReleaseMemObject','clReleaseKernel','clReleaseProgram','clReleaseCommandQueue','clReleaseContext'):
        release.append(api(lib,name,cl_int,[C.c_void_p]))
    count=cl_uint();check(get_platforms(0,None,C.byref(count)),'platform discovery')
    plats=(cl_platform*count.value)();check(get_platforms(count,plats,None),'platform discovery')
    selected=None;platform_name=''
    for plat in plats:
        name=info_string(get_pinfo,plat,PLATFORM_NAME)
        devcount=cl_uint();code=get_devices(plat,GPU,0,None,C.byref(devcount))
        if code==0 and devcount.value:
            ds=(cl_device*devcount.value)();check(get_devices(plat,GPU,devcount,ds,None),'GPU discovery')
            for dev in ds:
                if 'NVIDIA' in info_string(get_dinfo,dev,DEVICE_NAME):selected=(plat,dev);platform_name=name;break
        if selected:break
    if not selected:raise RuntimeError('NVIDIA OpenCL GPU not found; check NVIDIA driver OpenCL ICD')
    plat,dev=selected
    device_name=info_string(get_dinfo,dev,DEVICE_NAME);device_version=info_string(get_dinfo,dev,DEVICE_VERSION);driver=info_string(get_dinfo,dev,DRIVER_VERSION)
    err=cl_int();ctx=create_context(None,1,C.pointer(dev),None,None,C.byref(err));check(err.value,'context creation')
    queue=create_queue(ctx,dev,0,C.byref(err));check(err.value,'queue creation')
    src=Path(args.kernel).read_bytes();srcbuf=C.c_char_p(src);srcsize=C.c_size_t(len(src))
    program=create_program(ctx,1,C.byref(srcbuf),C.byref(srcsize),C.byref(err));check(err.value,'program creation')
    code=build(program,1,C.pointer(dev),b'-cl-std=CL1.2',None,None)
    if code:
        n=C.c_size_t();get_build(program,dev,BUILD_LOG,0,None,C.byref(n));log=C.create_string_buffer(n.value);get_build(program,dev,BUILD_LOG,n.value,log,None)
        raise RuntimeError('OpenCL inline-PTX kernel build failed: '+log.value.decode(errors='replace'))
    kernel=create_kernel(program,b'pearl_opencl_mma_probe',C.byref(err));check(err.value,'kernel creation')
    # Exact CPU oracle at K=128 catches PTX operand layout/sign errors before benchmark.
    test_a,test_b=make_data(128,1,8675309);result=(cl_int*(4*128))()
    def run(a_bytes,b_bytes,k,batches,warps,out):
        ah=C.create_string_buffer(a_bytes);bh=C.create_string_buffer(b_bytes)
        ab=create_buffer(ctx,MEM_READ_ONLY|MEM_COPY_HOST_PTR,len(a_bytes),ah,C.byref(err));check(err.value,'A buffer')
        bb=create_buffer(ctx,MEM_READ_ONLY|MEM_COPY_HOST_PTR,len(b_bytes),bh,C.byref(err));check(err.value,'B buffer')
        ob=create_buffer(ctx,MEM_WRITE_ONLY,len(out)*C.sizeof(cl_int),None,C.byref(err));check(err.value,'output buffer')
        kk=cl_uint(k);bn=cl_uint(batches)
        for i,v in enumerate((ab,bb,ob,kk,bn)):check(set_arg(kernel,i,C.sizeof(v),C.byref(v)),'kernel argument')
        glob=C.c_size_t(warps*32);local=C.c_size_t(128)
        check(enqueue(queue,kernel,1,C.byref(glob),None,C.byref(local),0,None,None),'kernel launch');check(finish(queue),'kernel finish')
        check(read(queue,ob,1,0,C.sizeof(out),out,0,None,None),'readback');check(finish(queue),'readback finish')
        for mem in (ab,bb,ob):release[0](mem)
    run(test_a,test_b,128,1,4,result)
    expected=cpu_reference(test_a,test_b,128)
    if list(result)[:128]!=expected:raise RuntimeError('K=128 OpenCL MMA differs from exact signed-int8 CPU reference')
    print('OpenCL tensor-core correctness: PASS (K=128, 16x8, exact CPU match)',flush=True)
    a_bytes,b_bytes=make_data(args.k,args.batches,8675310)
    ah=C.create_string_buffer(a_bytes);bh=C.create_string_buffer(b_bytes)
    ab=create_buffer(ctx,MEM_READ_ONLY|MEM_COPY_HOST_PTR,len(a_bytes),ah,C.byref(err));check(err.value,'benchmark A buffer')
    bb=create_buffer(ctx,MEM_READ_ONLY|MEM_COPY_HOST_PTR,len(b_bytes),bh,C.byref(err));check(err.value,'benchmark B buffer')
    out=(cl_int*(args.warps*128))()
    ob=create_buffer(ctx,MEM_WRITE_ONLY,len(out)*C.sizeof(cl_int),None,C.byref(err));check(err.value,'benchmark output buffer')
    kk=cl_uint(args.k);bn=cl_uint(args.batches)
    for i,v in enumerate((ab,bb,ob,kk,bn)):check(set_arg(kernel,i,C.sizeof(v),C.byref(v)),'benchmark kernel argument')
    glob=C.c_size_t(args.warps*32);local=C.c_size_t(128);samples=[]
    for _ in range(args.rounds):
        start=time.perf_counter()
        check(enqueue(queue,kernel,1,C.byref(glob),None,C.byref(local),0,None,None),'benchmark launch')
        check(finish(queue),'benchmark finish');samples.append(time.perf_counter()-start)
    median=sorted(samples)[len(samples)//2];ops=args.warps*16*8*args.k*2
    check(read(queue,ob,1,0,C.sizeof(out),out,0,None,None),'benchmark readback');check(finish(queue),'benchmark readback finish')
    print('OPENCL TENSOR PROBE:',json.dumps(dict(complete=True,pool_connection=False,submitted_shares=0,
        backend='OpenCL C + NVIDIA inline PTX mma.sync s8->s32',platform=platform_name,device=device_name,
        opencl_version=device_version,driver=driver,k=args.k,warps=args.warps,batches=args.batches,
        median_kernel_round_wall_s=median,estimated_integer_ops_per_second=ops/median,
        result_checksum=sum(int(x) for x in out)&0xffffffff,correctness='PASS K=128; timed K exact same kernel'),sort_keys=True),flush=True)
    for mem in (ab,bb,ob):release[0](mem)
    release[1](kernel);release[2](program);release[3](queue);release[4](ctx)

if __name__=='__main__':main()
