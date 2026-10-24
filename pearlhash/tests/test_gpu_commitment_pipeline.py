"""CPU tests of backend contracts and proof integration; no GPU claims. ISC."""
import hashlib
import unittest
from reference.native_hash import chunk_value
from reference.plain_proof import Tree
from tools.gpu_commitment import GpuCommitments,checked_tree,validate_inputs
from tools.offline_end_to_end import candidate,build_proof


class CpuBackend(GpuCommitments):
    def __init__(self):self.calls=[]
    def compute(self,first,key,data):
        count=validate_inputs(first,key,data);self.calls.append((first,count))
        return b''.join(chunk_value(data[i*1024:(i+1)*1024],first+i,key)for i in range(count))


class GpuCommitmentPipelineTests(unittest.TestCase):
    def test_batch_offsets_odd_tree_and_openings(self):
        device=CpuBackend();key=bytes(range(32))
        data=hashlib.shake_256(b'odd-tree-129-chunks').digest(129*1024-7)
        tree=checked_tree(data,key,device.chunk_cvs)
        self.assertEqual(device.calls,[(0,128),(128,1)])
        self.assertEqual(tree.layers,Tree(data,key).layers)
        opening=tree.opening([0,1,64,128],1024);opening.verify(key)
        # Single chunk uses root-domain hashing, never a leaf CV or a GPU call.
        device.calls.clear();single=checked_tree(b'small',key,device.chunk_cvs)
        self.assertEqual(device.calls,[]);self.assertEqual(single.layers,Tree(b'small',key).layers)

    def test_fresh_v2_v3_proof_bytes_match_cpu_pipeline(self):
        for version in (2,3):
            device=CpuBackend()
            reference=candidate(bytes(range(32)),version)
            actual=candidate(bytes(range(32)),version,tree_factory=lambda data,key:checked_tree(data,key,device.chunk_cvs))
            self.assertEqual(actual['gpu_input'],reference['gpu_input'])
            self.assertEqual(build_proof(actual),build_proof(reference))
            self.assertEqual(len(device.calls),4 if version==2 else 8)

    def test_corrupt_or_malformed_backend_fails_closed(self):
        key=bytes(32);data=bytes(2048);device=CpuBackend()
        def corrupt(raw,key):
            values=device.chunk_cvs(raw,key);values[0]=bytes(32);return values
        with self.assertRaisesRegex(ValueError,'differs'):
            checked_tree(data,key,corrupt)
        for bad in ([],[bytes(32)],[bytes(31),bytes(32)]):
            with self.assertRaisesRegex(ValueError,'invalid chaining'):
                Tree(data,key,leaf_hasher=lambda raw,key:bad)
        for first,raw in ((-1,b''),(1<<64,b''),((1<<64)-1,bytes(2048)),(0,bytes(1023))):
            with self.assertRaises(ValueError):validate_inputs(first,key,raw)
        for size in (0,4097,True):
            with self.assertRaises(ValueError):device.chunk_cvs(data,key,batch_chunks=size)

if __name__=='__main__':unittest.main()
