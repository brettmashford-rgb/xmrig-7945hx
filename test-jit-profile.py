#!/usr/bin/env python3
"""Small format/join contract tests. Requires objdump for code examples."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location('report', Path(__file__).with_name('report-jit-profile.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.trace = self.root / 'jit-trace.bin'
        self.sample = self.root / 'samples.txt'
        self.header = m.HEADER.pack(b'RXJIT01\0', 42, 7)
    def tearDown(self):
        self.temp.cleanup()
    def record(self, stamp, kind):
        return (m.RECORD.pack(stamp, 0x1000, 3, 0x100, 1, 1, 7, 0)
                + m.REGION.pack(0, 3, kind) + b'\x48\x01\xc0\xc3')
    def test_reuse_end_thread_and_epilogue(self):
        close = m.RECORD.pack(3000000000, 0, 0, 0, 0, 0, 7, 0)
        self.trace.write_bytes(self.header + self.record(1000000000, 0)
                               + self.record(2000000000, 10) + close)
        self.sample.write_text('7 1.500000000: 1001\n7 2.500000000: 1001\n'
                               '7 2.600000000: 1100\n7 3.100000000: 1001\n'
                               '8 2.500000000: 1001\n7 2.700000000: 9999\n')
        self.assertEqual(m.analyze(self.trace, self.sample, self.root), {0: 1, 10: 1, 36: 1})
    def test_truncation(self):
        self.trace.write_bytes(self.header + self.record(1, 0)[:-1])
        with self.assertRaises(ValueError):
            list(m.records(self.trace))
    def test_overlapping_regions(self):
        self.trace.write_bytes(self.header + m.RECORD.pack(1, 0x1000, 3, 0x100, 0, 2, 7, 0)
                               + m.REGION.pack(0, 2, 0) + m.REGION.pack(1, 3, 1) + b'abc')
        with self.assertRaises(ValueError):
            list(m.records(self.trace))
    def test_unexpected_sample_format(self):
        self.sample.write_text('this is not a sampled IP\n')
        with self.assertRaises(ValueError):
            m.samples(self.sample)
    def test_invalid_header(self):
        self.trace.write_bytes(b'broken')
        with self.assertRaises(ValueError):
            m.analyze(self.trace, self.sample, self.root)

if __name__ == '__main__':
    unittest.main()
