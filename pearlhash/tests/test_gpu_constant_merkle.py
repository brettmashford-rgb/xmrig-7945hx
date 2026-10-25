"""Compile the actual GPU core as host C++; compare independent CPU hashes/trees. ISC."""
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from reference.constant_merkle import constant_opening
from reference.native_hash import chunk_value,small_hash,parents
from tools.gpu_constant_merkle import ConstantMerkleGpu,validate

ROOT=Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name)
        source=folder/'core.cpp'
        source.write_text('''#include "constant_merkle_core.h"
extern "C" void leaf(const unsigned*key,unsigned fill,unsigned long long index,int root,
 const unsigned*tail,int use_tail,unsigned*out){ph_merkle::constant_chunk(key,fill,index,root,tail,use_tail,out);}
extern "C" void parent(const unsigned*children,const unsigned*key,int root,unsigned*out){ph_merkle::parent(children,key,root,out);}
''')
        subprocess.run(['g++','-O2','-shared','-fPIC','-std=c++17','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'core.so')],check=True)
        cls.lib=C.CDLL(str(folder/'core.so'))
        cls.lib.leaf.argtypes=[C.c_void_p,C.c_uint,C.c_ulonglong,C.c_int,C.c_void_p,C.c_int,C.c_void_p]
        cls.lib.parent.argtypes=[C.c_void_p,C.c_void_p,C.c_int,C.c_void_p]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def leaf(cls,key,fill,index,tail=b'',root=False):
        out=C.create_string_buffer(32);cls.lib.leaf(key,fill,index,root,tail or bytes(16),bool(tail),out)
        return out.raw

    def test_actual_core_leaf_counters_fill_tail_root_and_parents(self):
        for key in (bytes(32),bytes(range(32))):
            for fill in (0,64,255):
                for index in (0,1,255,(1<<32)+3,(1<<64)-1):
                    for tail in (b'',bytes(range(16))):
                        block=bytes([fill])*1024
                        if tail:block=block[:-16]+tail
                        self.assertEqual(self.leaf(key,fill,index,tail),chunk_value(block,index,key))
                        if index==0:self.assertEqual(self.leaf(key,fill,index,tail,True),small_hash(block,key))
            children=self.leaf(key,64,0)+self.leaf(key,64,1)
            for root in (False,True):
                out=C.create_string_buffer(32);self.lib.parent(children,key,root,out)
                self.assertEqual(out.raw,parents([children[:32],children[32:]],key,root=root)[0])

    def device(self):
        owner=self
        class Fake(ConstantMerkleGpu):
            def __init__(self):self.allocations=[];self.memory={};self.next=1000;self.corrupt=False
            def locate(self,address,size):
                address=address.value if hasattr(address,'value')else address
                for base,data in self.memory.items():
                    if base<=address and address+size<=base+len(data):return data,address-base
                raise ValueError('foreign fake GPU address')
            def api(self,name,types,*args):
                if name=='cuMemAlloc_v2':
                    C.cast(args[0],C.POINTER(C.c_ulonglong))[0]=self.next
                    self.memory[self.next]=bytearray(args[1]);self.next+=args[1]+64
                elif name=='cuMemcpyHtoD_v2':
                    data,offset=self.locate(args[0],args[2]);data[offset:offset+args[2]]=C.string_at(args[1],args[2])
                elif name=='cuMemcpyDtoH_v2':
                    data,offset=self.locate(args[1],args[2]);C.memmove(args[0],bytes(data[offset:offset+args[2]]),args[2])
                elif name=='cuMemFree_v2':self.memory.pop(args[0].value)
                elif name!='cuCtxSynchronize':raise AssertionError(name)
            def raw(self,pointer,size):
                data,offset=self.locate(pointer,size);return bytes(data[offset:offset+size])
            def store(self,pointer,index,raw):
                data,offset=self.locate(pointer.value+index*32,len(raw));data[offset:offset+len(raw)]=raw
            def launch(self,name,args,blocks,threads):
                if name==b'constant_merkle_leaves':
                    key,fill,count,tail,length,out=args;key=self.raw(key,32);tail=self.raw(tail,16)
                    for i in range(count.value):
                        value=owner.leaf(key,fill.value,i,tail if length.value==16 and i+1==count.value else b'',count.value==1)
                        self.store(out,i,value)
                    if self.corrupt:
                        data,offset=self.locate(out.value+count.value*32,16);data[offset]=0
                elif name==b'constant_merkle_parents':
                    children,key,count,out=args;key=self.raw(key,32)
                    for i in range((count.value+1)//2):
                        if i*2+1==count.value:value=self.raw(C.c_ulonglong(children.value+i*64),32)
                        else:
                            data=self.raw(C.c_ulonglong(children.value+i*64),64);result=C.create_string_buffer(32)
                            owner.lib.parent(data,key,count.value==2,result);value=result.raw
                        self.store(out,i,value)
                else:raise AssertionError(name)
        return Fake()

    def test_full_sparse_openings_match_independent_cpu_for_odd_and_power_two_trees(self):
        key=bytes(range(32))
        for total in (1,2,3,31,32,33,65,129):
            for tail in (b'',bytes(range(16))):
                device=self.device();rows=sorted({0,total//2,total-1})
                got=device.opening(key,64,total,rows,1024,tail=tail)
                expected=constant_opening(key,64,total,rows,1024,tail=tail)
                self.assertEqual(got.serialize(),expected.serialize())
                self.assertEqual(device.allocations,[]);self.assertEqual(device.memory,{})
        device=self.device()
        self.assertEqual(device.opening(key,64,96,[0,2],32768).serialize(),
                         constant_opening(key,64,96,[0,2],32768).serialize())

    def test_guards_cancellation_and_input_caps_release_only_owned_memory(self):
        key=bytes(32);device=self.device();device.corrupt=True
        with self.assertRaisesRegex(RuntimeError,'guard'):device.opening(key,64,2,[0],1024)
        self.assertEqual(device.allocations,[])
        device=self.device();calls=[]
        def current():
            calls.append(1)
            if len(calls)==2:raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):device.opening(key,64,33,[0],1024,current=current)
        self.assertEqual(device.allocations,[])
        for values in ((True,2,[0],1024,b''),(64,0,[0],1024,b''),(64,2,[1,0],1024,b''),
                       (64,2,[0],1000,b''),(64,2,[0],1024,b'x'),(64,8388608,list(range(129)),32768,b'')):
            with self.assertRaises(ValueError):validate(key,*values)


if __name__=='__main__':unittest.main()
