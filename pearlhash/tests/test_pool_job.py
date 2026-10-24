import unittest
from pool.job import Notify, header_from_payload


class PoolJobTests(unittest.TestCase):
    def test_controlled_range_payload_header(self):
        # Synthetic input and independently captured client-decoder output.
        expected = bytes.fromhex(
            'd0eea5baeadf611fc929837ec76d49221629fb19d3d1d48b39d758eb0b6d98911'
            '6e4d862fab9dfadefe2e38778b663c933d31b3f60eb182564cb49e4eb3c09221'
            '2785ad0f31b507757277ce1')
        self.assertEqual(header_from_payload(bytes(range(200))), expected)
        for tail in (bytes(124), bytes([255])*124):
            self.assertEqual(header_from_payload(bytes(range(76))+tail), expected)

    def test_strict_schema_and_opaque_fields(self):
        message = {'status': 1, 'id': -1, 'result': ['notify', bytes(range(200)).hex(),
                   bytes(range(32)).hex(), '0123456789abcdef', '3']}
        job = Notify.parse(message)
        self.assertEqual(job.target_bytes, bytes(range(32)))
        self.assertEqual(job.token.hex(), '0123456789abcdef')
        self.assertEqual(job.version_marker, '3')
        self.assertEqual(len(job.header), 76)
        for index, value in [(1, '00'*199), (1, '  '+'00'*199), (2, 'zz'*32),
                             (3, '00'*7), (4, '4'), (4, 3)]:
            bad = dict(message, result=list(message['result']))
            bad['result'][index] = value
            with self.assertRaises(ValueError):
                Notify.parse(bad)
        for size in (0, 76, 199, 201):
            with self.assertRaises(ValueError):
                header_from_payload(bytes(size))


if __name__ == '__main__':
    unittest.main()
