"""Host-only parser and CPU checks for the GPU harness (no GPU claims).

PEARL_GPU_CHECK must point to the compiled executable.
"""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


class HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = os.environ.get('PEARL_GPU_CHECK')
        if not cls.binary:
            raise unittest.SkipTest('set PEARL_GPU_CHECK to compiled executable')
        cls.vectors = Path(__file__).parent / 'gpu'

    def check_data(self, data, message):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.bin'
            path.write_bytes(data)
            p = subprocess.run([self.binary, '--cpu-only', str(path)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn(message, p.stderr)

    def test_seven_vectors(self):
        paths = sorted(self.vectors.glob('*.bin'))
        self.assertEqual(len(paths), 7)
        p = subprocess.run([self.binary, '--cpu-only', *map(str, paths)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout.count('PASS:'), 7)

    def test_malformed_inputs(self):
        data = (self.vectors / 'single-negative.bin').read_bytes()
        cases = [
            (b'wrong!!!' + data[8:], 'bad fixture magic'),
            (data[:-1], 'truncated fixture'),
            (data + b'!', 'trailing fixture bytes'),
            (data[:8] + struct.pack('<I', 0) + data[12:], 'unsupported dimensions'),
            (data[:20] + struct.pack('<I', 0) + data[24:], 'unsupported dimensions'),
            (data[:24] + struct.pack('<i', 128) + data[28:], 'outside [-127,127]'),
            (data[:-4] + bytes([data[-4] ^ 1]) + data[-3:], 'CPU transcript differs'),
        ]
        for payload, message in cases:
            with self.subTest(message=message):
                self.check_data(payload, message)


if __name__ == '__main__':
    unittest.main()
