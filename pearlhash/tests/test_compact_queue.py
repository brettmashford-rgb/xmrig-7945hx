"""Compact readback bounds, overflow semantics and complete candidate checks. ISC."""
import struct
import unittest
from unittest.mock import patch
from tools.stream_scan import StreamDispatch,populated_count
from tools.prepared_dispatch import KERNELS
from tools.check_tile_scan_gpu import TileQuery,MAX_BOUND
from tools.wide_scan import decode_wide
from test_prepared_dispatch import FakeDevice,FakeTables


class CompactQueue(unittest.TestCase):
    def test_original_capacity_is_validated_before_download_length(self):
        for total,overflow,capacity in ((10,0,9),(2,1,9),(2,0,1),(2,2,1),(1,0,0)):
            with self.assertRaises(ValueError):populated_count(struct.pack('<2I',total,overflow),[MAX_BOUND]*9,capacity,7)
        with self.assertRaises(ValueError):populated_count(bytes(4),[0],1,7)
    def test_complete_and_partial_decode_matches_original_full_buffer(self):
        for total,capacity in ((0,0),(0,9),(1,9),(3,9),(9,9),(9,3),(9,0)):
            status=struct.pack('<2I',total,int(total>capacity));bound=[MAX_BOUND]*9
            used=populated_count(status,bound,capacity,7)
            raw=b''.join(struct.pack('<3I',i,7,0)+bytes([i])*32 for i in range(used))
            compact=decode_wide(raw,status,bound,used,7)
            original=decode_wide(raw+bytes((capacity-used)*44),status,bound,capacity,7)
            self.assertEqual(compact,original)
    def test_empty_queue_reads_no_payload_but_still_checks_queue_guards(self):
        device=FakeDevice();tables=FakeTables(device);lane=StreamDispatch(device,tables,KERNELS[0])
        query=TileQuery(tuple(range(10)),tuple(range(16)))
        try:
            batch=lane.prepare([query]*9,[0]*9);lane.stage(batch,7,capacity=9);lane.enqueue()
            with patch.object(lane,'download',wraps=lane.download)as download:
                result,_=lane.finish()
                self.assertEqual(result.total,0)
                sizes=[call.args[1]for call in download.call_args_list if call.args[0]is lane.queue]
                self.assertEqual(sizes,[0])
            lane.stage(batch,7,capacity=9);lane.enqueue();device.memory[lane.queue[0].value][-1]=0
            with self.assertRaisesRegex(RuntimeError,'guard'):lane.finish()
        finally:lane.close()
    def test_invalid_status_does_not_read_candidate_payload(self):
        device=FakeDevice();tables=FakeTables(device);lane=StreamDispatch(device,tables,KERNELS[0])
        query=TileQuery(tuple(range(10)),tuple(range(16)))
        try:
            lane.stage(lane.prepare([query]*9,[0]*9),7,capacity=9);lane.enqueue()
            data,offset=device.locate(lane.status[1],0,8);data[offset:offset+8]=struct.pack('<2I',10,0)
            with patch.object(lane,'download',wraps=lane.download)as download:
                with self.assertRaises(ValueError):lane.finish()
                self.assertFalse(any(call.args[0]is lane.queue for call in download.call_args_list))
        finally:lane.close()
    def test_populated_candidate_reads_only_one_record_and_cpu_verifies_it(self):
        device=FakeDevice();tables=FakeTables(device);lane=StreamDispatch(device,tables,KERNELS[0])
        query=TileQuery(tuple(range(10)),tuple(range(16)))
        try:
            lane.stage(lane.prepare([query]*9,[MAX_BOUND]*9),7,capacity=9);lane.enqueue()
            data,offset=device.locate(lane.status[1],0,8);data[offset:offset+8]=struct.pack('<2I',1,0)
            data,offset=device.locate(lane.queue[1],0,44);data[offset:offset+44]=struct.pack('<3I',5,7,0)+bytes(32)
            with patch.object(lane,'download',wraps=lane.download)as download,\
                 patch('tools.stream_scan.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
                result,_=lane.finish();self.assertEqual(result.records,{5:bytes(32)})
                reference.assert_called_once();self.assertEqual(device.verified_tiles,1)
                self.assertEqual([call.args[1]for call in download.call_args_list if call.args[0]is lane.queue],[44])
        finally:lane.close()


if __name__=='__main__':unittest.main()
