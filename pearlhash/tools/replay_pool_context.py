#!/usr/bin/env python3
"""Offline reconstruction from a user-local existing-miner capture. No network code.

Observed dense profile only: sb=1 means enabled constant bias 64, empty sb_p,
tail_mode=1, rank 128. This is not a general pool client or consensus validator.
CPU streams full commitments/openings without materializing 8-GiB matrices;
the existing GPU checker validates selected math; the official CPU oracle
validates the independently built proof with an exactly represented share target.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from pool.job import Notify,hex_bytes
from reference.constant_merkle import constant_opening
from reference.dense import noise_rows,jackpot
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern
from reference.plain_proof import PlainProof
from reference.pool_nonce import nonce_tail
from reference.seeds import dense_noise_seeds


def compact_target(target):
    if type(target)is not int or not 0<target<1<<256:raise ValueError('invalid target')
    size=(target.bit_length()+7)//8
    word=target<<(8*(3-size))if size<=3 else target>>(8*(size-3))
    if word&0x800000:word>>=8;size+=1
    decoded=word>>(8*(3-size))if size<=3 else word<<(8*(size-3))
    if decoded!=target:raise ValueError('share target is not exactly representable as nBits')
    return size<<24|word


def profile(submit):
    if not isinstance(submit,dict)or submit.get('method')!='submit':raise ValueError('expected submit')
    params=submit.get('params')
    if not isinstance(params,list)or len(params)!=1 or not isinstance(params[0],dict):raise ValueError('invalid submit params')
    p=params[0]
    if any(type(p.get(k))is not int or p[k]!=1 for k in ('sb','tail_mode'))or p.get('sb_p')!=[]:
        raise ValueError('unsupported signal profile; never treat sb as a literal fill byte')
    for name in ('m','n','k','rank','tile_h','tile_w'):
        if type(p.get(name))is not int or p[name]<=0:raise ValueError('invalid dimensions')
    if p['rank']!=128 or not 1024<=p['k']<=65536 or p['k']%1024:
        raise ValueError('replay supports rank 128 and complete chunk rows only')
    if any(p[name]*p['k']>8*1024**3 for name in ('m','n')):
        raise ValueError('matrix exceeds 8-GiB streaming cap')
    patterns=[]
    for name,dimension,tile in (('a_rows','m','tile_h'),('b_cols','n','tile_w')):
        values=p.get(name)
        if (not isinstance(values,list)or not values or len(values)>32
            or any(type(v)is not int or not 0<=v<p[dimension]for v in values)
            or values!=sorted(set(values))or len(values)!=p[tile]):raise ValueError('invalid selected rows/columns')
        pattern=PeriodicPattern.from_list([v-values[0]for v in values])
        if not pattern.offset_is_valid(values[0]):raise ValueError('invalid tile offset')
        patterns.append(pattern.encoded)
    if p['tile_h']*p['tile_w']>256:raise ValueError('tile exceeds 256 elements')
    worker=hex_bytes(p.get('worker_nonce'),8);miner=hex_bytes(p.get('miner_nonce'),8)
    if hex_bytes(p.get('nonce'),8)!=miner:raise ValueError('nonce aliases differ')
    config=struct.pack('<IHH',p['k'],p['rank'],0)+b''.join(patterns)+bytes(32)
    return p,config,nonce_tail(worker,miner)


def reconstruct(header,submit,target,*,progress=print):
    if type(header)is not bytes or len(header)!=76 or type(target)is not bytes or len(target)!=32:
        raise ValueError('invalid header/target width')
    p,config,tail=profile(submit);key=small_hash(header+config)
    raw_target=int.from_bytes(target,'little');share_nbits=compact_target(raw_target)
    bound=raw_target*p['tile_h']*p['tile_w']*p['k'] # observed rank 128: neutral rank penalty
    if bound>=1<<256:raise ValueError('scaled target overflows u256; unsupported replay')
    progress('CPU: streaming A commitment and sparse openings...',flush=True)
    a=constant_opening(key,64,p['m']*p['k']//1024,p['a_rows'],p['k'],tail=tail)
    progress('CPU: streaming B commitment and sparse openings (8-GiB cap; no full matrix allocation)...',flush=True)
    b=constant_opening(key,64,p['n']*p['k']//1024,p['b_cols'],p['k'])
    bs,ass=dense_noise_seeds(key,a.root,b.root,p['m'],p['n'],cert_version=3)
    signals_a=[[64]*p['k']for _ in p['a_rows']];signals_b=[[64]*p['k']for _ in p['b_cols']]
    for i,row in enumerate(p['a_rows']):
        if row==p['m']-1:signals_a[i][-16:]=[v if v<128 else v-256 for v in tail]
    na=noise_rows(p['k'],p['rank'],p['a_rows'],b'A_tensor',ass)
    nb=noise_rows(p['k'],p['rank'],p['b_cols'],b'B_tensor',bs)
    aa=[[x+y for x,y in zip(signal,noise,strict=True)]for signal,noise in zip(signals_a,na,strict=True)]
    bb=[[x+y for x,y in zip(signal,noise,strict=True)]for signal,noise in zip(signals_b,nb,strict=True)]
    words=jackpot(aa,bb,p['rank']);digest=small_hash(struct.pack('<16I',*words),ass)
    if int.from_bytes(digest,'little')>bound:raise ValueError('reconstructed digest exceeds observed scaled share target')
    gpu=b'PHGPU02\0'+struct.pack('<4I',p['tile_h'],p['tile_w'],p['k'],p['rank'])
    for row in aa+bb:gpu+=struct.pack(f'<{p["k"]}i',*row)
    gpu+=struct.pack('<16I',*words)+ass+bs+struct.pack(f'<{p["tile_h"]+p["tile_w"]}I',*(p['a_rows']+p['b_cols']))
    for row in signals_a+signals_b:gpu+=struct.pack(f'<{p["k"]}i',*row)
    gpu+=digest
    proof=PlainProof(p['m'],p['n'],p['k'],p['rank'],a,b).serialize()
    facts={'config':config.hex(),'job_key':key.hex(),'root_a':a.root.hex(),'root_b':b.root.hex(),
           'a_seed':ass.hex(),'b_seed':bs.hex(),'tail':tail.hex(),'words':words,'digest':digest.hex(),
           'bound_le':bound.to_bytes(32,'little').hex(),'share_nbits':share_nbits}
    return gpu,proof,facts


def load_saved(path,submit_id,notify_packet,expected_sha256):
    if path.stat().st_size>8*1024*1024:raise ValueError('saved context exceeds cap')
    raw=path.read_bytes().removesuffix(b'\n')
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('saved context fingerprint differs')
    data=json.loads(raw);contexts=[c for c in data['contexts']if c['submit'].get('id')==submit_id]
    if len(contexts)!=1:raise ValueError('expected unique selected context')
    context=contexts[0];submit=context['submit'];reply=context['response']
    if reply.get('id')!=submit_id or reply.get('status')!=1 or reply.get('result')is not True:
        raise ValueError('captured response differs')
    records=[r for r in data['records']if r['connection']==context['connection']and r['direction']=='in'
             and r['packet']==notify_packet and r['packet']<context['packets'][0]
             and isinstance(r['json'].get('result'),list)and r['json']['result']
             and r['json']['result'][0]=='notify']
    if len(records)!=1:raise ValueError('expected unique selected preceding notify')
    notify=Notify.parse(records[0]['json'])
    if notify.version_marker!='3':raise ValueError('replay supports the explicit observed V3 profile only')
    return notify,submit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context',type=Path,required=True)
    parser.add_argument('--submit-id',type=int,required=True)
    parser.add_argument('--notify-packet',type=int,required=True)
    parser.add_argument('--expect-context-sha256',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--gpu-check',type=Path,required=True)
    parser.add_argument('--cubin',type=Path,required=True)
    args=parser.parse_args()
    for p in (args.oracle,args.gpu_check,args.cubin):
        if not p.is_file():raise ValueError(f'existing component missing: {p}')
    if len(args.expect_context_sha256)!=64 or any(v not in '0123456789abcdef'for v in args.expect_context_sha256):
        raise ValueError('expected lowercase SHA-256 for the private local context')
    notify,submit=load_saved(args.context,args.submit_id,args.notify_packet,args.expect_context_sha256)
    args.output_dir.mkdir(parents=True,exist_ok=False);out=args.output_dir.resolve()
    print('PASS: saved capture fingerprints match; existing-miner record only',flush=True)
    gpu,proof,facts=reconstruct(notify.header,submit,notify.target_bytes)
    print('PASS: complete streamed CPU commitments/openings authenticate and the reconstructed digest meets the selected target',flush=True)
    fixture=out/'captured-share-gpu.bin';fixture.write_bytes(gpu)
    subprocess.run([str(args.gpu_check.resolve()),str(args.cubin.resolve()),str(fixture)],check=True,timeout=240)
    verification={'cert_version':3,'header_base64':base64.b64encode(notify.header).decode(),
                  'plain_proof_base64':base64.b64encode(proof).decode(),'share_nbits':facts['share_nbits']}
    path=out/'captured-share-proof.json';path.write_text(json.dumps(verification,indent=2)+'\n')
    subprocess.run([str(args.oracle.resolve()),'verify',str(path)],check=True,timeout=240,
                   env=dict(os.environ,RAYON_NUM_THREADS='2'))
    manifest={'scope':'offline replay of captured existing-miner share; not a custom share or pool verdict',
              'private_context_sha256':args.expect_context_sha256,
              'selected_submit_id':args.submit_id,'selected_notify_packet':args.notify_packet,'gpu_math_checked':True,'official_cpu_verifier':'passed',
              'proof_sha256':hashlib.sha256(proof).hexdigest(),'proof_bytes':len(proof),'facts':facts}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS: independently reconstructed captured-share proof verified offline',flush=True)
    print('No pool connection, retransmission, custom share, service/clock change or performance claim.',flush=True)


if __name__=='__main__':main()
