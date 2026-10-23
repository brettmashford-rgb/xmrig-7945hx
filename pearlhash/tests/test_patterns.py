import unittest
from reference.patterns import PeriodicPattern


class PatternTests(unittest.TestCase):
    def test_pinned_fixture_pattern(self):
        p = PeriodicPattern(bytes.fromhex('000103010301'))
        self.assertEqual(p.shape, ((1, 2), (8, 2), (64, 2)))
        self.assertEqual(p.to_list(), [0, 1, 8, 9, 64, 65, 72, 73])
        self.assertEqual(PeriodicPattern.from_list(p.to_list()), p)
        self.assertEqual(p.period, 128)

    def test_observed_shapes_with_synthetic_offsets(self):
        rows = PeriodicPattern.from_list([0, 1, 8, 9, 16, 17, 24, 25, 32, 33])
        cols = PeriodicPattern.from_list([0, 1, 8, 9, 32, 33, 40, 41, 64, 65, 72, 73, 96, 97, 104, 105])
        self.assertEqual(rows.encoded.hex(), '000103040000')
        self.assertEqual(cols.encoded.hex(), '000103010103')
        self.assertEqual((rows.size, cols.size), (10, 16))
        self.assertEqual(rows.indices_with_offset(6), [6, 7, 14, 15, 22, 23, 30, 31, 38, 39])
        self.assertTrue(cols.offset_is_valid(4))
        self.assertFalse(rows.offset_is_valid(7))
        self.assertFalse(cols.offset_is_valid(8))

    def test_rejections_and_limits(self):
        for encoded in ('0000000000', '00000000000000', '010000000000',
                        '000100010000', '000000010000', 'ffffffffff00'):
            with self.assertRaises(ValueError):
                PeriodicPattern(bytes.fromhex(encoded))
        for values in ([], [1, 2], [0, 0], [0, 2, 1], [0, True], [0, 2, 3, 5],
                       [0, 1, 3], list(range(257)), [0, 2**32]):
            with self.assertRaises(ValueError):
                PeriodicPattern.from_list(values)
        p = PeriodicPattern(bytes(6))
        self.assertEqual(p.to_list(), [0])
        self.assertTrue(p.offset_is_valid(0xffffffff))
        for offset in (-1, 2**32, True):
            with self.assertRaises(ValueError):
                p.offset_is_valid(offset)


if __name__ == '__main__':
    unittest.main()
