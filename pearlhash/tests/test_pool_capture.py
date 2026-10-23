import struct
import unittest
from tools.inspect_pool_capture import inspect, reassemble


def packet(seq,body,syn=False):
    # Synthetic SLL2/IPv4/TCP, no live addresses or session payloads.
    link=struct.pack('!H',0x0800)+bytes(18)
    ip=bytearray(20);ip[0]=0x45;ip[9]=6
    struct.pack_into('!H',ip,2,40+len(body))
    tcp=bytearray(20);struct.pack_into('!HHI',tcp,0,9000,30000,seq)
    tcp[12]=0x50;tcp[13]=2 if syn else 0x10
    return link+ip+tcp+body


def pcap(packets):
    header=struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,276)
    return header+b''.join(struct.pack('<4I',0,0,len(p),len(p))+p for p in packets)


class CaptureTests(unittest.TestCase):
    def test_split_reordered_retransmitted_lines(self):
        data=pcap([packet(100,b'',True),packet(105,b'\nff\n'),
                   packet(101,b'6162'),packet(101,b'6162')])
        result=inspect(data)
        self.assertEqual(result['packets'],4)
        stream=result['streams'][0]
        self.assertTrue(stream['syn_seen'])
        self.assertEqual(stream['decoded_line_lengths'],[2,1])
        self.assertEqual(stream['incomplete_tail_bytes'],0)

    def test_wraparound(self):
        self.assertEqual(reassemble([(0xfffffffe,b'ab'),(0,b'cd')]),b'abcd')

    def test_fail_closed(self):
        for parts in [[(1,b'a'),(3,b'b')],[(1,b'ab'),(2,b'x')]]:
            with self.assertRaises(ValueError):reassemble(parts)
        for data in [pcap([packet(1,b'zz\n')]),pcap([packet(1,b'aa\n')])[:-1]]:
            with self.assertRaises(ValueError):inspect(data)
        with self.assertRaisesRegex(ValueError,'missing initial TCP bytes'):
            inspect(pcap([packet(100,b'',True),packet(102,b'aa\n')]))

    def test_mid_session_boundary_unknown(self):
        result=inspect(pcap([packet(1,b'aa\nbb')]))['streams'][0]
        self.assertFalse(result['first_line_boundary_verified'])
        self.assertEqual(result['incomplete_tail_bytes'],2)
