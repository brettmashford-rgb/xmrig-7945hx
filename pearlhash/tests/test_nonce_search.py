"""Fresh nonce/job/proof binding and real target-filter tests; CPU only. ISC."""
from dataclasses import replace
import unittest
from reference.plain_proof import PlainProof,Tree
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain,RangePlan
from tools.check_range_scan_gpu import ConstantProfile,RangeBackend
from tools.offline_nonce_search import (BOUND,K,M,N,NBITS,FoundTile,SyntheticJob,
    build_candidate,find_candidate,make_job,prepare_base,prepare_nonce)


class NonceSearchTests(unittest.TestCase):
    def test_roots_match_full_trees_nonce_changes_a_and_explicit_v3_seeds(self):
        seed=bytes(range(32));job=make_job(seed,2);base=prepare_base(job)
        worker=bytes(range(8));miner=bytes(range(8,16))
        context=prepare_nonce(job,base,worker,miner,1)
        a=bytes([64])*(M*K-16)+context.profile.tail;b=bytes([64])*(N*K)
        self.assertEqual(context.root_a,Tree(a,job.job_key).root)
        self.assertEqual(base.opening.root,Tree(b,job.job_key).root)
        other=prepare_nonce(job,base,worker,bytes([99])*8,2)
        self.assertNotEqual(context.profile.tail,other.profile.tail)
        self.assertNotEqual(context.root_a,other.root_a)
        self.assertEqual(context.base.opening.root,other.base.opening.root)
        salted=prepare_nonce(make_job(seed,3),base,worker,miner,3)
        self.assertEqual(context.root_a,salted.root_a)
        self.assertNotEqual(context.profile.seed_a,salted.profile.seed_a)
        with self.assertRaises(ValueError):prepare_nonce(make_job(bytes([1])*32,2),base,worker,miner,4)
        with self.assertRaises(ValueError):prepare_nonce(job,base,worker,miner,True)
        with self.assertRaises(ValueError):SyntheticJob(job.header[:-4]+(NBITS+1).to_bytes(4,'little'),2)

    def test_fresh_target_candidate_proof_matches_full_trees_and_rejects_stale(self):
        for version in (2,3):
            job=make_job(bytes(range(32)),version);base=prepare_base(job)
            context=prepare_nonce(job,base,bytes(range(8)),bytes(range(8,16)),version)
            found,cursor=find_candidate(context)
            self.assertIsNotNone(found);self.assertGreater(cursor.next_tile,0)
            self.assertLessEqual(int.from_bytes(found.digest,'little'),BOUND)
            proof,_=build_candidate(context,found);decoded=PlainProof.parse(proof)
            a=Tree(bytes([64])*(M*K-16)+context.profile.tail,job.job_key)
            b=Tree(bytes([64])*(N*K),job.job_key)
            self.assertEqual(decoded.a.serialize(),a.opening(decoded.a.rows,K).serialize())
            self.assertEqual(decoded.bt.serialize(),b.opening(decoded.bt.rows,K).serialize())
            for bad in (replace(found,generation=99),replace(found,digest=(BOUND+1).to_bytes(32,'little')),
                        replace(found,digest=bytes(32))):
                with self.assertRaises(ValueError):build_candidate(context,bad)
            with self.assertRaises(ValueError):build_candidate(replace(context,root_a=bytes(32)),found)
            other=prepare_nonce(job,base,context.worker,bytes([99])*8,context.generation)
            with self.assertRaises(ValueError):build_candidate(other,found)

    def test_cpu_backend_uses_actual_bound_and_retries_only_matching_hits(self):
        pattern=PeriodicPattern(bytes(6));plan=RangePlan(PatternDomain(2,pattern),PatternDomain(3,pattern))
        batch=next(plan.batches(0,6))
        profile=ConstantProfile(2,3,2048,128,64,bytes(16),bytes(32),bytes([1])*32)
        full=RangeBackend(profile);all_hits=full(batch,6,7)
        self.assertEqual(all_hits.total,6)
        target=sorted(int.from_bytes(d,'little')for d in all_hits.records.values())[2]
        backend=RangeBackend(profile,bound=target)
        partial=backend(batch,1,7);self.assertTrue(partial.overflow)
        with self.assertRaises(RuntimeError):partial.require_complete()
        actual=backend(batch,6,7).require_complete()
        expected={i:d for i,d in all_hits.records.items()if int.from_bytes(d,'little')<=target}
        self.assertEqual(actual,expected);self.assertGreaterEqual(len(actual),3)
        self.assertEqual(RangeBackend(profile,bound=0)(batch,6,7).total,0)


if __name__=='__main__':unittest.main()
