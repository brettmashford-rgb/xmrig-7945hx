"""Reusable dispatch serialization, generations, overflow and ownership. ISC."""
import ctypes as C
from dataclasses import replace
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import TileQuery
from tools.prepared_dispatch import QueryPacker, PreparedDispatch, KERNELS
from tools.wide_scan import pack_wide


def profile():
    return ConstantProfile(5121,262144,32768,128,64,bytes(16),bytes(32),bytes(32))


class FakeDevice:
    def __init__(self):
        self.module=C.c_void_p(1); self.memory={}; self.next=1000; self.allocations=[]
        self.calls=[]; self.after_launch=None
        self.verified_tiles=0; self.unique_cpu_checks=0; self.dispatches=0; self.wide_dispatches=0
    def guarded(self,size):
        raw=C.c_ulonglong(self.next); self.next+=size+64
        self.memory[raw.value]=bytearray(b'\xa5'*(size+32)); self.allocations.append(raw)
        return raw,C.c_ulonglong(raw.value+16)
    def locate(self,pointer,offset,size):
        address=pointer.value+offset
        for base,data in self.memory.items():
            if base<=address and address+size<=base+len(data):return data,address-base
        raise ValueError('unowned device read')
    def api(self,name,types,*args):
        self.calls.append(name)
        if name=='cuMemcpyHtoD_v2':
            data,off=self.locate(args[0],0,args[2]); data[off:off+args[2]]=C.string_at(args[1],args[2])
        elif name=='cuLaunchKernel' and self.after_launch:self.after_launch()
    def release(self,pointer):
        self.memory.pop(pointer.value); self.allocations.remove(pointer)


class FakeTables:
    def __init__(self,device):
        self.device=device; self.profile=profile(); self.closed=False; self.key_a=C.c_ulonglong(1)
    def inputs(self):return tuple(C.c_ulonglong(i)for i in range(5))
    def check_guards(self):pass
    def read(self,pointer,offset,size):
        data,off=self.device.locate(pointer,offset,size);return bytes(data[off:off+size])


class DispatchTests(unittest.TestCase):
    def queries(self):
        return (TileQuery(tuple(range(10)),tuple(range(16))),)*16
    def test_descriptor_bytes_match_original_for_global_and_mapped_indices(self):
        p=profile(); q=self.queries()+ (TileQuery(tuple(range(5120,5110,-1)),tuple(range(262143,262127,-1))),)
        packer=QueryPacker(p); owner=object(); prepared=packer.prepare(owner,q,[0]*len(q),0)
        self.assertEqual(prepared.descriptors,pack_wide(p,q))
        maps=({v:i for i,v in enumerate(sorted({v for x in q for v in x.rows}))},
              {v:i for i,v in enumerate(sorted({v for x in q for v in x.cols}))})
        cache=SimpleNamespace(maps=maps,closed=False,tables=SimpleNamespace(closed=False))
        mapped=tuple(TileQuery(tuple(maps[0][v]for v in x.rows),tuple(maps[1][v]for v in x.cols))for x in q)
        expected=pack_wide(replace(p,m=len(maps[0]),n=len(maps[1])),mapped)
        self.assertEqual(QueryPacker(p,cache).prepare(owner,q,[0]*len(q),0).descriptors,expected)
        # Equal booleans must not bypass prior integer validation.
        bad=TileQuery((False,)+q[0].rows[1:],q[0].cols)
        with self.assertRaises(ValueError):packer.prepare(owner,[bad],[0],0)
        with self.assertRaises(ValueError):packer.prepare(owner,[TileQuery((-1,)+q[0].rows[1:],q[0].cols)],[0],0)
    def test_reuse_uploads_only_status_and_frees_only_owned_allocations(self):
        device=FakeDevice(); tables=FakeTables(device)
        unrelated,_=device.guarded(4)
        dispatch=PreparedDispatch(device,tables,KERNELS[0],capacity=0)
        batch=dispatch.prepare(self.queries(),[0]*16)
        before=len(device.allocations)
        self.assertEqual(dispatch.run(batch,1<<63).total,0)
        device.calls.clear(); self.assertEqual(dispatch.run(batch,(1<<63)+1).total,0)
        self.assertEqual(device.calls.count('cuMemcpyHtoD_v2'),1)
        second_batch=dispatch.prepare(tuple(reversed(batch.queries)),batch.bounds)
        device.calls.clear();dispatch.run(second_batch,(1<<63)+1)
        self.assertEqual(device.calls.count('cuMemcpyHtoD_v2'),3)
        self.assertEqual(len(device.allocations),before)
        self.assertEqual(dispatch.generation.value,(1<<63)+1)
        dispatch.close(); dispatch.close()
        self.assertEqual(device.allocations,[unrelated])
        with self.assertRaises(ValueError):dispatch.run(batch,0)
    def test_stale_before_and_after_launch_foreign_batches_and_guards(self):
        device=FakeDevice(); tables=FakeTables(device)
        first=PreparedDispatch(device,tables,KERNELS[0],capacity=0)
        second=PreparedDispatch(device,tables,KERNELS[0],capacity=0)
        batch=first.prepare(self.queries(),[0]*16)
        with self.assertRaisesRegex(ValueError,'foreign'):second.run(batch,1)
        device.calls.clear()
        with self.assertRaisesRegex(RuntimeError,'stale'):first.run(batch,1,current=lambda:2)
        self.assertNotIn('cuLaunchKernel',device.calls)
        generation=[1];device.after_launch=lambda:generation.__setitem__(0,2)
        with self.assertRaisesRegex(RuntimeError,'stale'):first.run(batch,1,current=lambda:generation[0])
        device.after_launch=None
        device.memory[first.queue[0].value][-1]=0
        with self.assertRaisesRegex(RuntimeError,'guard'):first.run(batch,1)
        first.close();second.close()
    def test_partial_queue_does_not_cpu_verify_and_complete_queue_does(self):
        device=FakeDevice(); tables=FakeTables(device)
        dispatch=PreparedDispatch(device,tables,KERNELS[0],capacity=1)
        batch=dispatch.prepare(self.queries(),[(1<<256)-1]*16)
        def write(total,overflow):
            data,off=device.locate(dispatch.status[1],0,8);data[off:off+8]=struct.pack('<2I',total,overflow)
            data,off=device.locate(dispatch.queue[1],0,44)
            data[off:off+44]=struct.pack('<3I',0,5,0)+bytes(32)
        with patch('tools.prepared_dispatch.global_reference',return_value=[(bytes(64),bytes(32))])as reference:
            device.after_launch=lambda:write(16,1)
            self.assertTrue(dispatch.run(batch,5).overflow);reference.assert_not_called()
            device.after_launch=lambda:write(1,0)
            self.assertFalse(dispatch.run(batch,5).overflow);reference.assert_called_once()
        self.assertEqual(device.verified_tiles,1)
        device.after_launch=None
        self.assertEqual(dispatch.run(batch,5).records,{})
        dispatch.close()

    def test_changing_grid_is_unique_and_each_window_is_collective_shaped(self):
        from tools.check_prepared_gpu import grid
        from tools.cooperative_scan import validate_cooperative
        rows,cols,queries,cover=grid(profile())
        self.assertEqual(len(set(queries)),8192)
        for first in range(0,8192,1024):validate_cooperative(queries[first:first+1024])
        self.assertEqual({r for q in cover for r in q.rows},{r for q in queries for r in q.rows})
        self.assertEqual({c for q in cover for c in q.cols},{c for q in queries for c in q.cols})


if __name__=='__main__':unittest.main()
