"""Cached A roots/contexts equal full native tree recomputation, including irregular trees. ISC."""
from dataclasses import replace,FrozenInstanceError
import secrets
import unittest
from unittest.mock import patch
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.check_prepared_job import synthetic_session
from tools.compare_search_loops import production_session
from pool.search import prepare_base,prepare_nonce,StaleWork
from reference.constant_merkle import constant_opening


class Frontier(unittest.TestCase):
    def setUp(self):self.session,self.job,self.message=synthetic_session(bytes(32))
    def tearDown(self):self.session.close()
    def test_irregular_and_power_of_two_shapes_match_full_tree(self):
        for m in (40,64,96,128,160,5121):
            profile=replace(self.job.profile,m=m);job=replace(self.job,profile=profile)
            cache=NonceCommitmentCache.build(job,lambda candidate:True)
            for tail in (bytes(16),bytes(range(16)),bytes([255])*16):
                expected=constant_opening(job.job_key,64,m*32,[0],32768,tail=tail).root
                self.assertEqual(cache.root(tail),expected)
            if m==5121:self.assertEqual(len(cache.siblings),7)
    def test_complete_nonce_context_matches_existing_path(self):
        base=prepare_base(self.job,self.session.is_current);cache=NonceCommitmentCache.build(self.job,self.session.is_current)
        for miner in (bytes(8),b'12345678',secrets.token_bytes(8)):
            old=prepare_nonce(self.job,base,b'TESTWORK',miner,self.session.is_current)
            new=prepare_cached_nonce(self.job,base,b'TESTWORK',miner,self.session.is_current,cache)
            self.assertEqual(old,new)
    def test_no_full_tree_call_after_frontier_construction(self):
        base=prepare_base(self.job,self.session.is_current);cache=NonceCommitmentCache.build(self.job,self.session.is_current)
        with patch('tools.nonce_cache.constant_opening',side_effect=AssertionError('full tree repeated')):
            prepare_cached_nonce(self.job,base,b'TESTWORK',bytes(8),self.session.is_current,cache)
    def test_frontier_is_frozen_and_corruption_rejected(self):
        cache=NonceCommitmentCache.build(self.job,self.session.is_current)
        with self.assertRaises(FrozenInstanceError):cache.m=1
        with self.assertRaises(ValueError):replace(cache,siblings=(bytes(32),*cache.siblings[1:]))
        with self.assertRaises(ValueError):replace(cache,siblings=cache.siblings[:-1])
        with self.assertRaises(ValueError):replace(cache,key=bytes(32))
        with self.assertRaises(ValueError):replace(cache,_ticket=None)
    def test_wrong_job_or_dimensions_rejected_before_using_frontier(self):
        base=prepare_base(self.job,self.session.is_current);cache=NonceCommitmentCache.build(self.job,self.session.is_current)
        for job in (replace(self.job,job_key=bytes(32)),replace(self.job,profile=replace(self.job.profile,m=161))):
            with self.assertRaises(ValueError):prepare_cached_nonce(job,base,b'TESTWORK',bytes(8),lambda candidate:True,cache)
    def test_bad_nonce_or_tail_types_rejected(self):
        base=prepare_base(self.job,self.session.is_current);cache=NonceCommitmentCache.build(self.job,self.session.is_current)
        for tail in (bytes(15),bytes(17),bytearray(16),None):
            with self.assertRaises(ValueError):cache.root(tail)
        for nonce in (bytes(7),bytes(9),bytearray(8),None):
            with self.assertRaises(ValueError):prepare_cached_nonce(self.job,base,nonce,bytes(8),self.session.is_current,cache)
    def test_stale_before_and_after_root_computation_rejected(self):
        base=prepare_base(self.job,self.session.is_current);cache=NonceCommitmentCache.build(self.job,self.session.is_current)
        with self.assertRaises(StaleWork):prepare_cached_nonce(self.job,base,b'TESTWORK',bytes(8),lambda job:False,cache)
        current=[True];original=NonceCommitmentCache.root
        def changed(instance,tail):
            root=original(instance,tail);current[0]=False;return root
        with patch.object(NonceCommitmentCache,'root',changed):
            with self.assertRaises(StaleWork):prepare_cached_nonce(self.job,base,b'TESTWORK',bytes(8),lambda job:current[0],cache)
    def test_stale_after_native_cache_build_rejected(self):
        current=[True];original=constant_opening
        def changed(*args,**kwargs):
            result=original(*args,**kwargs);current[0]=False;return result
        with patch('tools.nonce_cache.constant_opening',side_effect=changed):
            with self.assertRaises(StaleWork):NonceCommitmentCache.build(self.job,lambda job:current[0])


if __name__=='__main__':unittest.main()
