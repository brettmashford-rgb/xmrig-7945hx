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

    def test_five_noise_digest_vectors(self):
        paths=sorted((self.vectors.parent/'gpu-noise').glob('*.bin'))
        self.assertEqual(len(paths),5)
        p=subprocess.run([self.binary,'--cpu-only',*map(str,paths)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(p.stdout.count('noise + products + transcript + digest:'),5)

    def test_invalid_noise_digest_inputs(self):
        data=(self.vectors.parent/'gpu-noise/rank1024.bin').read_bytes()
        rows,cols,k,rank=struct.unpack_from('<4I',data,8)
        extension=24+4*(rows+cols)*k+64
        indices=extension+64
        signals=indices+4*(rows+cols)
        def replace(offset,value):
            return data[:offset]+struct.pack('<I',value)+data[offset+4:]
        cases=[
            (data[:extension]+bytes([data[extension]^1])+data[extension+1:], 'CPU noise differs'),
            (replace(indices,0xffffffff), 'noise row index overflow'),
            (replace(signals,65), 'signal outside [-64,64]'),
            (data[:-1]+bytes([data[-1]^1]), 'CPU digest differs'),
            (data[:-1], 'truncated fixture'),
            (data+b'!', 'trailing fixture bytes'),
        ]
        for payload,message in cases:
            with self.subTest(message=message):
                self.check_data(payload,message)


if __name__ == '__main__':
    unittest.main()
