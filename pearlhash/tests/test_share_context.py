import unittest
from tools.capture_share_context import contexts, complete_prefix
from tools.decode_pool_capture import decode_capture
from tools.pool_probe import encode
from test_decode_pool_capture import inbound, outbound
from test_pool_capture import pcap

TOKEN = '0123456789abcdef'
NOTIFY = {'status': 1, 'id': -1, 'result': ['notify', '00'*200, '00'*32, TOKEN, '3']}
SUBMIT = {'id': 4, 'method': 'submit', 'params': [{'worker_nonce': TOKEN}]}
REPLY = {'status': 1, 'id': 4, 'result': True}


def capture(notify=NOTIFY, submit=SUBMIT, reply=REPLY, late=False, other=False):
    n, s, r = (encode(m, 10) for m in (notify, submit, reply))
    packets = [inbound(1, n, client=30001 if other else 30000), outbound(1, s), inbound(1+len(n), r)]
    if late:
        packets = [outbound(1, s), inbound(1, n), inbound(1+len(n), r)]
    return pcap(packets)


class ShareContextTests(unittest.TestCase):
    def test_earlier_notify_and_unique_true_response(self):
        selected = contexts(decode_capture(capture()))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['packets'], [2, 3])
        self.assertEqual(selected[0]['preceding_notifies'][0]['packet'], 1)
        self.assertEqual(selected[0]['submit'], SUBMIT)
        for data in (capture(late=True), capture(other=True),
                     capture(reply=dict(REPLY, result=False)), capture(reply=dict(REPLY, status=0))):
            self.assertEqual(contexts(decode_capture(data)), [])
        # Do not confuse the opaque notify token with a submitted worker_nonce.
        selected = contexts(decode_capture(capture(submit=dict(SUBMIT, params=[{'worker_nonce': 'f'*16}]))))
        self.assertEqual(len(selected), 1)

    def test_multiple_notifies_are_candidates_not_assigned_jobs(self):
        one = encode(NOTIFY, 10)
        two = encode(dict(NOTIFY, result=['notify', 'ff'*200, '00'*32, TOKEN, '3']), 10)
        data = pcap([inbound(1, one+two), outbound(1, encode(SUBMIT, 10)),
                     inbound(1+len(one+two), encode(REPLY, 10))])
        selected = contexts(decode_capture(data))[0]
        self.assertEqual(len(selected['preceding_notifies']), 2)
        self.assertIn('unverified', selected['job_association'])

    def test_live_snapshot_trims_only_incomplete_last_record(self):
        data = capture()
        for end in range(len(data)):
            prefix = complete_prefix(data[:end])
            if prefix:
                self.assertEqual(complete_prefix(prefix), prefix)
                decode_capture(prefix)
        self.assertEqual(complete_prefix(data), data)
        with self.assertRaises(ValueError):
            complete_prefix(b'x'*24)


if __name__ == '__main__':
    unittest.main()
