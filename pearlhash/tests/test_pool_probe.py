import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pool_probe', Path(__file__).resolve().parents[1] / 'tools/pool_probe.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Stream:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True
    def sendall(self, data):
        self.sent.append(data)
    def settimeout(self, value):
        pass
    def recv(self, size):
        # Deliberately split ASCII hex and LF boundaries.
        part, self.reply = self.reply[:min(7, size)], self.reply[min(7, size):]
        return part


class PoolProbeTests(unittest.TestCase):
    def test_independent_encoder_golden(self):
        # Controlled legacy encoder output for 48 ASCII 'A', nonce 10.
        expected = bytes.fromhex('638bdfd745dbfd3d7b9357f9fd4581ef95532f0f31c387310be91905db734b670f5c559547633f79186725e55d95b385')
        self.assertEqual(p.transform(b'A' * 48, 10), expected)
        # Complete synthetic legacy encoder frame: arbitrary ASCII body '{}'.
        self.assertEqual(p.encode({}, 10), b'0000000a59b7\n')
        self.assertEqual(p.decode(b'0000000a59b7\n'), {})

    def test_roundtrip_boundaries(self):
        for nonce in (10, 11, 255, 256, 65535, 65536, 0x7fffffff, 0x80000000, 0xfffffffe):
            for length in (0, 1, 47, 48, 49, 192, 1024):
                obj = {'id': -1, 'result': ['notify', 'a' * length, '\u2603', True, None]}
                self.assertEqual(p.decode(p.encode(obj, nonce)), obj)
        for nonce in (0, 9, 0xffffffff, -1):
            with self.assertRaises(ValueError):
                p.encode({}, nonce)

    def test_reject_invalid_frames(self):
        for line in (b'', b'00', b'00\n', b'0000000a59b\n', b'0000000a59 b7\n',
                     b'0000000a59zg\n', b'f' * p.MAX_LINE + b'\n'):
            with self.assertRaises(ValueError):
                p.decode(line)
        for body in (b'[]', b'null', b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff'):
            line = (b'\0\0\0\x0a' + p.transform(body, 10)).hex().encode() + b'\n'
            with self.assertRaises((ValueError, UnicodeError)):
                p.decode(line)

    def test_probe_sends_only_login(self):
        reply = b''.join(p.encode(x, 10) for x in (
            {'status': 1, 'id': 0, 'result': True},
            {'status': 1, 'id': -1, 'result': ['extranonce', '00' * 8]},
            {'status': 1, 'id': -1, 'result': ['notify', 'ab' * 200, '00' * 32, '12' * 8, '3']},
        ))
        stream = Stream(reply)
        with tempfile.TemporaryDirectory() as tmp, patch('builtins.print'):
            output = Path(tmp) / 'capture.json'
            self.assertEqual(p.probe('example.invalid', 9000, 'synthetic-wallet', 'test', output,
                                     connect=lambda *a, **k: stream), 0)
            saved = json.loads(output.read_text())
            self.assertEqual(saved['submitted_shares'], 0)
            self.assertEqual(len(saved['records']), 4)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(stream.sent), 1)
            self.assertEqual(p.decode(stream.sent[0])['params'][-1], p.AGENT)
            self.assertTrue(stream.closed)
            with self.assertRaises(FileExistsError):
                p.probe('example.invalid', 9000, 'x', 'x', output)

    def test_rejected_login_and_truncation(self):
        for reply in (p.encode({'status': 0, 'id': 0, 'result': False}, 10), b'001122'):
            stream = Stream(reply)
            with tempfile.TemporaryDirectory() as tmp, patch('builtins.print'):
                output = Path(tmp) / 'capture.json'
                self.assertEqual(p.probe('example.invalid', 9000, 'x', 'x', output,
                                         connect=lambda *a, **k: stream), 1)
                self.assertTrue(json.loads(output.read_text())['error'])
                self.assertEqual(len(stream.sent), 1)
                self.assertTrue(stream.closed)


if __name__ == '__main__':
    unittest.main()
