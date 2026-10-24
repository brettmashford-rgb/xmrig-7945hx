import struct
import unittest

from tools.decode_pool_capture import decode_capture, describe
from tools.pool_probe import encode, transform
from test_pool_capture import packet, pcap


def outbound(seq, body, client=30000, syn=False):
    data = bytearray(packet(seq, body, syn))
    struct.pack_into('!HH', data, 40, client, 9000)
    return bytes(data)


def inbound(seq, body, client=30000, syn=False):
    data = bytearray(packet(seq, body, syn))
    struct.pack_into('!HH', data, 40, 9000, client)
    return bytes(data)


class DecodeCaptureTests(unittest.TestCase):
    def test_capture_order_and_late_gap_fill(self):
        first = encode({'id': 1, 'method': 'report_info'}, 10)
        second = encode({'id': 2, 'method': 'submit'}, 10)
        reply = encode({'status': 1, 'id': 2, 'result': True}, 10)
        notify = encode({'id': -1, 'result': ['notify']}, 10)
        # Second frame arrives first; neither can be consumed until the gap fills.
        report = decode_capture(pcap([
            outbound(100, b'', syn=True),
            outbound(101+len(first), second),
            inbound(400, notify),
            outbound(101, first), inbound(400+len(notify), reply),
            outbound(101, first+second),  # retransmission must not retime frames
        ]))
        self.assertEqual([r['json']['id'] for r in report['records']], [-1, 1, 2, 2])
        self.assertEqual([r['packet'] for r in report['records']], [3, 4, 4, 5])
        self.assertTrue(report['submits'][0]['response']['result'])

    def test_response_before_request_is_not_matched(self):
        report = decode_capture(pcap([
            inbound(1, encode({'status': 1, 'id': 8, 'result': True}, 10)),
            outbound(1, encode({'id': 8, 'method': 'submit'}, 10)),
        ]))
        self.assertIsNone(report['submits'][0]['response'])
        self.assertTrue(report['submits'][0]['response_before_request'])

    def test_frame_order_at_sequence_wrap_and_timestamp_precision(self):
        line = encode({'id': 8, 'method': 'submit'}, 10)
        data = bytearray(pcap([outbound(0xfffffff0, line[:16]), outbound(0, line[16:])]))
        # Nanosecond classic PCAP; completion belongs to packet two.
        data[:4] = b'\x4d\x3c\xb2\xa1'
        offset = 24+16+len(outbound(0xfffffff0, line[:16]))
        struct.pack_into('<II', data, offset, 123, 456789123)
        record = decode_capture(bytes(data))['records'][0]
        self.assertEqual(record['packet'], 2)
        self.assertEqual(record['timestamp_ns'], 123456789123)

    def test_submit_and_report_correlation(self):
        requests = b''.join(encode(m, 10) for m in (
            {'id': 7, 'method': 'report_info', 'params': []},
            {'id': 8, 'method': 'submit', 'params': [{'nonce': 'synthetic'}]},
        ))
        replies = b''.join(encode(m, 11) for m in (
            {'status': 1, 'id': 7, 'result': True},
            {'status': 0, 'id': 8, 'result': False},
        ))
        data = pcap([outbound(100, b'', syn=True), inbound(200, b'', syn=True),
                     outbound(101, requests[:19]), outbound(120, requests[19:]),
                     inbound(201, replies)])
        report = decode_capture(data)
        self.assertEqual(len(report['submits']), 1)
        self.assertFalse(report['submits'][0]['response']['result'])
        self.assertFalse(report['submits'][0]['ambiguous_id'])
        self.assertEqual(report['warnings'], [])

    def test_no_share_inferred_from_report(self):
        data = pcap([outbound(1, encode({'id': 7, 'method': 'report_info'}, 10)),
                     inbound(2, encode({'status': 1, 'id': 7, 'result': True}, 10))])
        self.assertEqual(decode_capture(data)['submits'], [])

    def test_duplicate_ids_and_other_connections(self):
        submit = encode({'id': 8, 'method': 'submit'}, 10)
        reply = encode({'status': 1, 'id': 8, 'result': True}, 10)
        report = decode_capture(pcap([outbound(1, submit), inbound(2, reply, client=30001)]))
        self.assertIsNone(report['submits'][0]['response'])
        for requests, replies in ((submit+submit, reply), (submit, reply+reply)):
            report = decode_capture(pcap([outbound(1, requests), inbound(2, replies)]))
            self.assertTrue(report['submits'][0]['ambiguous_id'])
            self.assertIsNone(report['submits'][0]['response'])

    def test_partial_boundaries_and_fail_closed(self):
        line = encode({'id': 8, 'method': 'submit'}, 10)
        report = decode_capture(pcap([outbound(1, b'bad-fragment\n'+line+b'partial')]))
        self.assertEqual(len(report['submits']), 1)
        self.assertEqual(len(report['warnings']), 3)
        for packets in ([outbound(1, line+b'bad\n')],
                        [outbound(1, b'', syn=True), outbound(2, b'bad\n')],
                        [outbound(1, line[:10]), outbound(12, line[10:])]):
            with self.assertRaises(ValueError):
                decode_capture(pcap(packets))

    def test_large_submit_bounded_console(self):
        import json
        message = {'id': 1, 'method': 'submit', 'params': [{'proof': 'a'*70000}]}
        body = json.dumps(message, separators=(',', ':')).encode()
        line = (b'\0\0\0\x0a'+transform(body, 10)).hex().encode()+b'\n'
        packets = [outbound(1+i, line[i:i+16000]) for i in range(0, len(line), 16000)]
        report = decode_capture(pcap(packets))
        self.assertEqual(len(report['submits']), 1)
        summary = describe(report['submits'][0]['request'])
        self.assertEqual(summary['params'][0]['proof']['string_characters'], 70000)
        self.assertEqual(describe(list(range(33))), {'array_length': 33})


if __name__ == '__main__':
    unittest.main()
