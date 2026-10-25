"""Candidate queue gates, independent hit checking and malformed results. ISC."""
import struct
import unittest

from tools.candidate_scan import decode_queue, verify_returned
from tools.check_tile_scan_gpu import MAX_BOUND


def wire(records, capacity):
    raw = b''.join(struct.pack('<IQ', tile, generation) + digest
                   for tile, generation, digest in records)
    return raw + bytes(capacity * 44 - len(raw))


class CandidateScanTests(unittest.TestCase):
    def test_unordered_complete_hits_only(self):
        digest = (7).to_bytes(32, 'little')
        raw = wire([(3, 0x123456789abcdef0, digest), (1, 0x123456789abcdef0, digest)], 4)
        result = decode_queue(raw, struct.pack('<2I', 2, 0), [MAX_BOUND]*4, 4, 0x123456789abcdef0)
        checked = []
        def reference(query):
            checked.append(query)
            return digest
        self.assertEqual(verify_returned(result, list(range(4)), reference), 2)
        self.assertEqual(checked, [3, 1])
        self.assertEqual(set(result.require_complete()), {1, 3})

    def test_empty_and_partial_queues_do_not_recompute(self):
        def unexpected(query):
            self.fail('miss or partial queue was recomputed')
        empty = decode_queue(bytes(44*4), bytes(8), [0]*4, 4, 19)
        self.assertEqual(verify_returned(empty, list(range(4)), unexpected), 0)
        for capacity in (0, 1):
            records = [(0, 19, bytes(32))] if capacity else []
            result = decode_queue(wire(records, capacity), struct.pack('<2I', 4, 1),
                                  [MAX_BOUND]*4, capacity, 19)
            self.assertEqual(verify_returned(result, list(range(4)), unexpected), 0)
            with self.assertRaises(RuntimeError):
                result.require_complete()

    def test_corrupt_counts_flags_lengths_and_tags(self):
        digest = (8).to_bytes(32, 'little')
        good = wire([(0, 19, digest)], 2)
        bad = [
            (good, struct.pack('<2I', 3, 1)),
            (good, struct.pack('<2I', 1, 1)),
            (good, struct.pack('<2I', 1, 2)),
            (good[:-1], struct.pack('<2I', 1, 0)),
            (good, bytes(7)),
            (wire([(2, 19, digest)], 2), struct.pack('<2I', 1, 0)),
            (wire([(0, 20, digest)], 2), struct.pack('<2I', 1, 0)),
            (wire([(0, 19, digest), (0, 19, digest)], 2), struct.pack('<2I', 2, 0)),
        ]
        for raw, status in bad:
            with self.subTest(raw=raw, status=status), self.assertRaises(ValueError):
                decode_queue(raw, status, [MAX_BOUND]*2, 2, 19)

    def test_equality_bound_and_independent_math_failure(self):
        digest = (8).to_bytes(32, 'little')
        raw = wire([(0, 19, digest)], 1)
        result = decode_queue(raw, struct.pack('<2I', 1, 0), [8], 1, 19)
        self.assertEqual(verify_returned(result, [None], lambda query: digest), 1)
        with self.assertRaises(ValueError):
            decode_queue(raw, struct.pack('<2I', 1, 0), [7], 1, 19)
        with self.assertRaises(ValueError):
            verify_returned(result, [None], lambda query: bytes(32))


if __name__ == '__main__':
    unittest.main()
