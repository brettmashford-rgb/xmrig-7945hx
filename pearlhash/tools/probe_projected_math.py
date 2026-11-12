"""Optional development probe; requires NumPy and the existing CPU reference library. ISC."""
import sys,time,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.compare_cta_b import production_session
from pool.search import prepare_base
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from reference.dense import _random_hash,noise_rows,jackpot
import struct
session,job=production_session();base=prepare_base(job,session.is_current);cache=NonceCommitmentCache.build(job,session.is_current)
context=prepare_cached_nonce(job,base,b'TESTWORK',bytes(8),session.is_current,cache);p=context.profile
pairs=[]
for i in range(p.k//8):
 for value in struct.unpack('<8I',_random_hash(i,b'B_tensor',p.seed_b,1)):
  first=value&127;second=first^(1+((127*value)>>32));pairs.append((first,second))
pairs=np.array(pairs,np.int32).reshape(256,128,2)
rows=list(range(63))+[p.m-1];a=np.asarray(noise_rows(p.k,p.rank,rows,b'A_tensor',p.seed_a),np.int32)
a[-1,-16:]+=np.frombuffer(p.tail,dtype=np.int8).astype(np.int32)-64
x=np.zeros((len(rows),256,128),np.int32);s=np.zeros((256,128),np.int32)
for q in range(256):
 np.add.at(x[:,q,:],(np.arange(len(rows))[:,None],pairs[q,:,0][None,:]),a[:,q*128:(q+1)*128])
 np.add.at(x[:,q,:],(np.arange(len(rows))[:,None],pairs[q,:,1][None,:]),-a[:,q*128:(q+1)*128])
 s[q]=np.bincount(pairs[q,:,0],minlength=128)-np.bincount(pairs[q,:,1],minlength=128)
lo=x.astype(np.int8).astype(np.int32);hi=(x-lo)//256;counts=np.count_nonzero(hi,axis=2)
print(json.dumps(dict(projected_coefficients=x.size,exception_fraction=float(np.count_nonzero(hi)/x.size),max_exceptions_per_row_checkpoint=int(counts.max()),mean_exceptions_per_row_checkpoint=float(counts.mean()),projection_min=int(x.min()),projection_max=int(x.max()),hi_min=int(hi.min()),hi_max=int(hi.max()),b_coeff_min=int(s.min()),b_coeff_max=int(s.max()))))
cols=list(range(16));ub=[]
for index in cols:
 values=[]
 for block in range(index*4,index*4+4):values.extend((v&63)-32 for v in _random_hash(block,b'B_tensor',p.seed_b,0))
 ub.append(values)
ub=np.array(ub,np.int64);bnoise=np.array(noise_rows(p.k,p.rank,cols,b'B_tensor',p.seed_b),np.int64).reshape(16,256,128)
assert np.array_equal(ub@s.T,bnoise.sum(axis=2))
selected=[*range(9),63];aa=a[selected].astype(np.int64).reshape(10,256,128)
actual=np.einsum('iqk,jqk->qij',aa+64,bnoise+64,dtype=np.int64)
reform=np.einsum('iqr,jr->qij',lo[selected].astype(np.int64),ub,dtype=np.int64)+256*np.einsum('iqr,jr->qij',hi[selected].astype(np.int64),ub,dtype=np.int64)+64*aa.sum(axis=2).T[:,:,None]+64*bnoise.sum(axis=2).T[:,None,:]+4096*128
assert np.array_equal(actual,reform)
prefix=actual.cumsum(axis=0); assert np.all((prefix>=-(1<<31))&(prefix<(1<<31)))
words=[0]*16
for q,matrix in enumerate(prefix):
 folded=0
 for value in matrix.flat:folded^=int(value)&0xffffffff
 slot=q%16;v=words[slot];words[slot]=(((v<<13)|(v>>19))&0xffffffff)^folded
scalar=jackpot((aa.reshape(10,32768)+64).tolist(),(bnoise.reshape(16,32768)+64).tolist(),128)
assert words==scalar
print('PASS exact 256 checkpoints / 160 accumulator cells / scalar transcript, including nonce tail')
session.close()
