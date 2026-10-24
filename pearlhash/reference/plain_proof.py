"""Independent dense commitment, Merkle opening and bincode-1 proof construction.

Pinned specification: pearl-blake3/src/{hasher,merkle}.rs and
zk-pow/src/ffi/plain_proof.rs at 82e6eee7076aafe10123e08db78f100d270c0582.
Materialized trees are capped at 64 MiB. A separate constant streaming backend
supports larger sparse openings. This does not implement every consensus rule.
"""
from dataclasses import dataclass
import struct
from reference.native_hash import chunk_cvs,chunk_value,parents,small_hash,key_check


def u64(value):
    if type(value) is not int or not 0<=value<2**64:raise ValueError('expected u64')
    return struct.pack('<Q',value)


def indices(values):
    return u64(len(values))+b''.join(u64(v) for v in values)


@dataclass
class Opening:
    leaves:list[bytes]
    leaf_indices:list[int]
    total_leaves:int
    root:bytes
    siblings:list[bytes]
    rows:list[int]

    def serialize(self):
        return (u64(len(self.leaves))+b''.join(u64(len(v))+v for v in self.leaves)
                +indices(self.leaf_indices)+u64(self.total_leaves)+self.root
                +u64(len(self.siblings))+b''.join(self.siblings)+indices(self.rows))

    def verify(self,key):
        key_check(key)
        if (not 1<=self.total_leaves<=8388608 or len(self.leaves)!=len(self.leaf_indices)
            or not self.leaf_indices or self.leaf_indices!=sorted(set(self.leaf_indices))
            or self.leaf_indices[0]<0 or self.leaf_indices[-1]>=self.total_leaves
            or any(len(v)!=1024 for v in self.leaves) or len(self.root)!=32
            or any(len(v)!=32 for v in self.siblings)):
            raise ValueError('invalid Merkle opening structure')
        if self.total_leaves==1:
            actual=small_hash(self.leaves[0],key)
            if self.siblings or actual!=self.root:raise ValueError('Merkle root mismatch')
            return
        nodes={i:chunk_value(data,i,key) for i,data in zip(self.leaf_indices,self.leaves,strict=True)}
        cursor=0;length=self.total_leaves
        while length>1:
            current=dict(nodes)
            for i in sorted(nodes):
                sib=i^1
                if sib<length and sib not in current:
                    if cursor>=len(self.siblings):raise ValueError('missing Merkle sibling')
                    current[sib]=self.siblings[cursor];cursor+=1
            next_level={}
            for parent in sorted({i//2 for i in nodes}):
                left=2*parent;right=left+1
                next_level[parent]=(parents([current[left],current[right]],key,root=length==2)[0]
                                    if right<length else current[left])
            nodes=next_level;length=(length+1)//2
        if cursor!=len(self.siblings) or nodes[0]!=self.root:raise ValueError('Merkle root mismatch')


class Tree:
    def __init__(self,data,key,*,leaf_hasher=None):
        key_check(key)
        if not isinstance(data,bytes) or not data or len(data)>64*1024*1024:
            raise ValueError('commitment input must contain 1 byte..64 MiB')
        self.data=data+bytes((-len(data))%1024);self.key=key
        if len(self.data)==1024:self.layers=[[small_hash(self.data,key)]]
        else:
            leaves=list((leaf_hasher or chunk_cvs)(self.data,key))
            if len(leaves)!=len(self.data)//1024 or any(type(v) is not bytes or len(v)!=32 for v in leaves):
                raise ValueError('leaf backend returned invalid chaining values')
            self.layers=[leaves]
            while len(self.layers[-1])>2:
                layer=self.layers[-1];paired=len(layer)//2*2
                self.layers.append(parents(layer[:paired],key)+(layer[-1:] if len(layer)%2 else []))
            self.layers.append(parents(self.layers[-1],key,root=True))
        self.root=self.layers[-1][0]

    def opening(self,rows,width):
        if (not rows or rows!=sorted(set(rows)) or rows[0]<0 or width<=0
            or (rows[-1]+1)*width>len(self.data)):
            raise ValueError('invalid opening rows/width')
        selected=sorted({i for row in rows for i in range(row*width//1024,((row+1)*width-1)//1024+1)})
        leaves=[self.data[i*1024:(i+1)*1024] for i in selected]
        active=set(selected);siblings=[];length=len(self.layers[0]);level=0
        while length>1:
            for i in sorted(active):
                sib=i^1
                if sib<length and sib not in active:siblings.append(self.layers[level][sib])
            active={i//2 for i in active};length=(length+1)//2;level+=1
        return Opening(leaves,selected,len(self.layers[0]),self.root,siblings,list(rows))


@dataclass
class PlainProof:
    m:int
    n:int
    k:int
    rank:int
    a:Opening
    bt:Opening

    def serialize(self):
        return b''.join(u64(v) for v in [self.m,self.n,self.k,self.rank])+self.a.serialize()+self.bt.serialize()+b'\0'

    @classmethod
    def parse(cls,data):
        if not isinstance(data,bytes) or len(data)>8*1024*1024:raise ValueError('proof size unsupported')
        pos=0
        def take(size):
            nonlocal pos
            if size<0 or pos+size>len(data):raise ValueError('truncated proof')
            value=data[pos:pos+size];pos+=size;return value
        def number():return struct.unpack('<Q',take(8))[0]
        def count(limit):
            n=number()
            if n>limit:raise ValueError('proof count exceeds limit')
            return n
        def ints():return [number() for _ in range(count(65536))]
        def opening():
            leaves=[]
            for _ in range(count(65536)):
                if number()!=1024:raise ValueError('leaf must be 1024 bytes')
                leaves.append(take(1024))
            ix=ints();total=number();root=take(32)
            siblings=[take(32) for _ in range(count(65536))]
            return Opening(leaves,ix,total,root,siblings,ints())
        dims=[number() for _ in range(4)];a=opening();bt=opening()
        if take(1)!=b'\0':raise ValueError('only dense proofs supported')
        if pos!=len(data):raise ValueError('trailing proof bytes')
        return cls(*dims,a,bt)
