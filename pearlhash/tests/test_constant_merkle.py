"""Streaming sparse proofs and observed profile checks; CPU only. ISC."""
import copy
import unittest
from reference.constant_merkle import constant_opening
from reference.plain_proof import Tree
from tools.replay_pool_context import compact_target,profile


class ConstantMerkleTests(unittest.TestCase):
    def test_streamed_openings_match_materialized_trees(self):
        for count in (1,2,3,7,16,31,129,257):
            for tail in (b'',bytes(range(16))):
                data=bytes([64])*(count*1024)
                if tail:data=data[:-16]+tail
                rows=sorted({0,count//2,count-1});key=bytes(range(32))
                actual=constant_opening(key,64,count,rows,1024,tail=tail)
                expected=Tree(data,key).opening(rows,1024)
                self.assertEqual(actual.serialize(),expected.serialize(),(count,len(tail)))
                changed=copy.deepcopy(actual);changed.leaves[0]=bytes(1024)
                with self.assertRaises(ValueError):changed.verify(key)

    def test_streaming_request_bounds(self):
        key=bytes(32)
        for args in ((True,2,[0],1024),(64,0,[0],1024),(64,8388609,[0],1024),
                     (64,2,[1,0],1024),(64,2,[2],1024),(64,2,[0],0)):
            with self.assertRaises(ValueError):constant_opening(key,*args)
        with self.assertRaises(ValueError):constant_opening(key,64,2,[0],1024,tail=b'x')

    def test_exact_share_nbits_and_flag_semantics(self):
        self.assertEqual(compact_target(1<<127),0x11008000)
        for value in (0,-1,1<<256,(1<<127)+1):
            with self.assertRaises(ValueError):compact_target(value)
        submit={'method':'submit','params':[{'sb':1,'sb_p':[],'tail_mode':1,'m':3,'n':4,'k':1024,
                'rank':128,'tile_h':1,'tile_w':1,'a_rows':[0],'b_cols':[1],
                'worker_nonce':'00'*8,'miner_nonce':'00'*8,'nonce':'00'*8}]}
        p,config,tail=profile(submit);self.assertEqual((len(config),len(tail)),(52,16))
        for field,value in (('sb',64),('rank',32),('nonce','01'*8),('tile_h',2)):
            changed=copy.deepcopy(submit);changed['params'][0][field]=value
            with self.assertRaises(ValueError):profile(changed)

if __name__=='__main__':unittest.main()
