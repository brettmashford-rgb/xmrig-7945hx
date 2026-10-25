"""Inclusive-target probability arithmetic, replacement classification and no private output. ISC."""
from dataclasses import replace
import math
import unittest
from pool.telemetry import WorkTelemetry
from test_submission import fixture


class TelemetryTests(unittest.TestCase):
    def test_inclusive_target_and_independent_trial_model(self):
        state,job,_=fixture();job=replace(job,share_bound=(1<<255)-1)
        tracker=WorkTelemetry(clock=lambda:10);tracker.received(job)
        tracker.add(job,tiles=2,nonces=1);tracker.seconds(job,'search',3.5)
        result=tracker.snapshot()
        self.assertEqual(result['expected_candidate_count'],1)
        self.assertAlmostEqual(result['model_probability_at_least_one_candidate'],0.75)
        self.assertEqual(result['jobs'][0]['mean_tiles_per_candidate'],2)
        self.assertEqual(result['jobs'][0]['seconds']['search'],3.5)
        # Returned nested dictionaries must not mutate accumulated accounting.
        result['jobs'][0]['seconds']['search']=999
        self.assertEqual(tracker.snapshot()['jobs'][0]['seconds']['search'],3.5)

    def test_changed_fields_are_booleans_not_captured_values(self):
        state,job,_=fixture();tracker=WorkTelemetry();tracker.received(job)
        tracker.received(replace(job,generation=job.generation+1,target_bytes=b'X'*32,
                                 share_bound=job.share_bound//2,opaque_token=b'Y'*8))
        result=tracker.snapshot();row=result['jobs'][1]
        self.assertEqual(row['changes'],{'header':False,'target':True,'extranonce':False,'metadata':False,'token':True})
        self.assertEqual(result['completed_tiles'],0)
        self.assertEqual(result['model_probability_at_least_one_candidate'],0)
        self.assertNotIn('job_key',row);self.assertNotIn('assigned_extranonce',row)

    def test_extreme_bounds_and_invalid_work(self):
        state,job,_=fixture();tracker=WorkTelemetry();tracker.received(replace(job,share_bound=(1<<256)-1))
        tracker.add(job,tiles=1,full_nonces=1)
        self.assertEqual(tracker.snapshot()['model_probability_at_least_one_candidate'],1)
        tracker=WorkTelemetry();tracker.received(replace(job,share_bound=0));tracker.add(job,tiles=1)
        result=tracker.snapshot()
        self.assertTrue(math.isfinite(result['expected_candidate_count']))
        self.assertGreater(result['model_probability_at_least_one_candidate'],0)
        for work in (-1,True):
            with self.assertRaises(ValueError):tracker.add(job,tiles=work)
        with self.assertRaises(ValueError):tracker.seconds(job,'search',float('nan'))


if __name__=='__main__':unittest.main()
