import base64
import copy
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
from reference.native_hash import small_hash
from reference.plain_proof import Tree,PlainProof
from tools.offline_end_to_end import candidate,build_proof


class ProofTests(unittest.TestCase):
    def test_native_hashes_and_roots_against_independent_library(self):
        try:from blake3 import blake3
        except ImportError:self.skipTest('independent Python blake3 library not installed')
        rng=random.Random(506005);key=rng.randbytes(32)
        for n in [0,1,7,63,64,65,127,128,511,1023,1024]:
            data=rng.randbytes(n)
            self.assertEqual(small_hash(data),blake3(data).digest())
            self.assertEqual(small_hash(data,key),blake3(data,key=key).digest())
        for n in [1,1024,2048,3072,5120,7168,262144]:
            tree=Tree(rng.randbytes(n),key)
            self.assertEqual(tree.root,blake3(tree.data,key=key).digest())

    def test_merkle_membership_and_tampering(self):
        key=bytes(range(32));data=bytes(i%251 for i in range(7*1024));tree=Tree(data,key)
        proof=tree.opening([0,2,6],1024);proof.verify(key)
        for kind in ['leaf','sibling','root','indices','extra-sibling']:
            p=copy.deepcopy(proof)
            if kind=='leaf':p.leaves[0]=bytes([p.leaves[0][0]^1])+p.leaves[0][1:]
            if kind=='sibling':p.siblings[0]=bytes([p.siblings[0][0]^1])+p.siblings[0][1:]
            if kind=='root':p.root=bytes([p.root[0]^1])+p.root[1:]
            if kind=='indices':p.leaf_indices=list(reversed(p.leaf_indices))
            if kind=='extra-sibling':p.siblings.append(bytes(32))
            with self.subTest(kind=kind),self.assertRaises(ValueError):p.verify(key)

    def test_original_official_generated_bytes_and_openings(self):
        vectors=Path(os.environ.get('PEARL_VECTORS_DIR',Path(__file__).parent/'vectors'))
        if not (vectors/'official-v2.json').is_file():self.skipTest('original JSON vectors not in this archive')
        for version in [2,3]:
            f=json.loads((vectors/f'official-v{version}.json').read_text())
            raw=base64.b64decode(f['plain_proof_base64']);proof=PlainProof.parse(raw)
            self.assertEqual(proof.serialize(),raw)
            proof.a.verify(bytes(f['job_key']));proof.bt.verify(bytes(f['job_key']))

    def test_fresh_proofs_official_acceptance_and_rejection(self):
        oracle=os.environ.get('PEARL_ORACLE')
        if not oracle:self.skipTest('set PEARL_ORACLE to pinned official verifier')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.json'
            def check(value,expected):
                path.write_text(json.dumps(value))
                proc=subprocess.run([oracle,'verify',str(path)],capture_output=True,text=True,
                                    env=dict(os.environ,RAYON_NUM_THREADS='2'),timeout=120)
                self.assertEqual(proc.returncode==0,expected,proc.stdout+proc.stderr)
            for version in [2,3]:
                c=candidate(bytes([version])*32,version);raw=build_proof(c)
                proof=PlainProof.parse(raw);self.assertEqual(proof.serialize(),raw)
                original={'cert_version':version,'header_base64':base64.b64encode(c['header']).decode(),
                          'plain_proof_base64':base64.b64encode(raw).decode(),'share_nbits':None}
                check(original,True)
                for kind in ['leaf','root','missing-sibling','header','tiny-target']:
                    value=dict(original);p=PlainProof.parse(raw)
                    if kind=='leaf':p.a.leaves[0]=bytes([p.a.leaves[0][0]^1])+p.a.leaves[0][1:]
                    if kind=='root':p.a.root=bytes([p.a.root[0]^1])+p.a.root[1:]
                    if kind=='missing-sibling':p.a.siblings.pop()
                    if kind=='header':value['header_base64']=base64.b64encode(bytes([c['header'][0]^1])+c['header'][1:]).decode()
                    if kind=='tiny-target':value['share_nbits']=0x01010000
                    value['plain_proof_base64']=base64.b64encode(p.serialize()).decode()
                    with self.subTest(version=version,kind=kind):check(value,False)

    def test_parser_rejects_bad_encoding(self):
        c=candidate(bytes(32),2);raw=build_proof(c)
        for bad in [raw[:-1],raw+b'!',raw[:-1]+b'\1',raw[:32]+struct.pack('<Q',65537)+raw[40:]]:
            with self.assertRaises(ValueError):PlainProof.parse(bad)
