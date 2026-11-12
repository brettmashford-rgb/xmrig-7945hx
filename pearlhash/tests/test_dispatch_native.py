"""Real compiled C bridge against scripted CUDA callbacks; no actual GPU claims. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import os,struct,subprocess,tempfile,unittest
from unittest.mock import patch
from pool.search import prepare_base,StaleWork
from pool.session import MiningProfile
from tools.nonce_cache import NonceCommitmentCache,prepare_cached_nonce
from tools.check_prepared_job import synthetic_session
from tools.dispatch_scan import new_search,MODES,KernelParams,MemsetParams,native_library,Api,Call
from tools.job_b_tables import JobBTables
from tools.job_geometry import JobGeometry
from tools.check_pair_depth import restore_retained_guard
from test_job_b_tables import Device

ROOT=Path(__file__).resolve().parents[1]


class NativeDevice(Device):
    def __init__(self):
        super().__init__();self.context=C.c_void_p(123);self.graphs={};self.executables={};self.nodes={};self.next_graph=100000
        self.fail_graph=None;self.error_native=None;self.native_occurrences={};self.callback_error=None;self.seen_scans=[]
        self.lib=SimpleNamespace();self.callbacks=[]
        defs=[('cuMemsetD32Async',(C.c_ulonglong,C.c_uint,C.c_size_t,C.c_void_p)),
            ('cuLaunchKernel',(C.c_void_p,)+(C.c_uint,)*7+(C.c_void_p,C.POINTER(C.c_void_p),C.POINTER(C.c_void_p))),
            ('cuStreamSynchronize',(C.c_void_p,)),('cuMemcpyDtoH_v2',(C.c_void_p,C.c_ulonglong,C.c_size_t)),
            ('cuGraphExecKernelNodeSetParams',(C.c_void_p,C.c_void_p,C.POINTER(KernelParams))),
            ('cuGraphLaunch',(C.c_void_p,C.c_void_p))]
        for name,kinds in defs:
            callback=C.CFUNCTYPE(C.c_int,*kinds)(self.callback(name))
            self.callbacks.append(callback);setattr(self.lib,name,callback)
    def callback(self,name):
        def invoke(*args):
            self.native_occurrences[name]=self.native_occurrences.get(name,0)+1
            if self.error_native==(name,self.native_occurrences[name]):return 777
            try:
                if name=='cuMemsetD32Async':args=(C.c_ulonglong(args[0]),args[1],args[2],C.c_void_p(args[3]))
                elif name=='cuLaunchKernel':args=(C.c_void_p(args[0]),)+args[1:8]+(C.c_void_p(args[8]),args[9],args[10])
                elif name=='cuStreamSynchronize':args=(C.c_void_p(args[0]),)
                elif name=='cuMemcpyDtoH_v2':args=(args[0],C.c_ulonglong(args[1]),args[2])
                elif name=='cuGraphExecKernelNodeSetParams':args=(C.c_void_p(args[0]),C.c_void_p(args[1]),args[2])
                elif name=='cuGraphLaunch':args=tuple(C.c_void_p(v)for v in args)
                # Call the scripted driver itself, bypassing any Python API instrumentation.
                NativeDevice.api(self,name,[],*args);return 0
            except BaseException as error:self.callback_error=error;return 999
        return invoke
    def handle(self):self.next_graph+=1;return self.next_graph
    def copy_kernel(self,pointer):
        k=KernelParams.from_buffer_copy(C.string_at(pointer,C.sizeof(KernelParams)))
        kinds=((C.c_ulonglong,)*11+(C.c_uint,)*7+(C.c_int,C.c_ulonglong,C.c_ulonglong)+(C.c_uint,)*3
               if k.func==self.functions.get(b'a_pair_direct_scan')else(C.c_ulonglong,)*3+(C.c_uint,C.c_ulonglong,C.c_uint,C.c_uint))
        values=tuple(kind(C.cast(k.params[i],C.POINTER(kind)).contents.value)for i,kind in enumerate(kinds))
        params=(C.c_void_p*len(values))(*(C.cast(C.byref(v),C.c_void_p)for v in values))
        k.params=params;k.values=values;k.storage=params;return k
    def api(self,name,types,*args):
        if name==self.fail_graph:raise RuntimeError('injected '+name)
        if name=='cuGraphCreate':
            self.calls.append(name);h=self.handle();self.graphs[h]=[];C.cast(args[0],C.POINTER(C.c_void_p))[0]=h;return
        if name in('cuGraphAddMemsetNode','cuGraphAddKernelNode'):
            self.calls.append(name);out,graph,deps,count,parameters=args[:5];h=self.handle()
            expected=()if not self.graphs[graph.value]else(self.graphs[graph.value][-1],)
            assert tuple(deps[i]for i in range(count))==expected
            if name=='cuGraphAddMemsetNode':
                p=MemsetParams.from_buffer_copy(C.string_at(parameters,C.sizeof(MemsetParams)))
                assert(p.value,p.element_size,p.width,p.height)==(0,4,2,1);assert args[5].value==self.context.value
                data=('reset',p)
            else:data=('kernel',self.copy_kernel(parameters))
            self.nodes[h]=data;self.graphs[graph.value].append(h);C.cast(out,C.POINTER(C.c_void_p))[0]=h;return
        if name=='cuGraphInstantiateWithFlags':
            self.calls.append(name);out,graph,flags=args;assert len(self.graphs[graph.value])==3 and flags==0
            h=self.handle();self.executables[h]=dict(graph=graph.value,updates={});C.cast(out,C.POINTER(C.c_void_p))[0]=h;return
        if name=='cuGraphExecKernelNodeSetParams':
            self.calls.append(name);executable,node,parameters=args
            assert node.value in self.graphs[self.executables[executable.value]['graph']]
            self.executables[executable.value]['updates'][node.value]=self.copy_kernel(parameters);return
        if name=='cuGraphLaunch':
            self.calls.append(name);executable,stream=args;info=self.executables[executable.value]
            for node in self.graphs[info['graph']]:
                kind,data=self.nodes[node]
                if kind=='reset':NativeDevice.api(self,'cuMemsetD32Async',[],C.c_ulonglong(data.dst),0,2,stream)
                else:
                    k=info['updates'].get(node,data)
                    NativeDevice.api(self,'cuLaunchKernel',[],C.c_void_p(k.func),k.gx,k.gy,k.gz,k.bx,k.by,k.bz,k.shared,stream,k.params,None)
            return
        if name=='cuGraphExecDestroy':self.calls.append(name);del self.executables[args[0].value];return
        if name=='cuGraphDestroy':
            self.calls.append(name)
            for node in self.graphs.pop(args[0].value):del self.nodes[node]
            return
        if name=='cuLaunchKernel'and args[0].value==self.functions.get(b'a_pair_direct_scan'):
            params=args[9]
            values=tuple(C.cast(params[i],C.POINTER(C.c_uint if i!=19 else C.c_ulonglong)).contents.value for i in(23,13,12,11,19))
            self.seen_scans.append(values)
        super().api(name,types,*args)


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.library=Path(cls.temp.name)/'bridge.so'
        subprocess.run(['gcc','-O3','-std=c11','-fPIC','-shared','-Wall','-Wextra','-Werror',str(ROOT/'host/dispatch_bridge.c'),'-o',str(cls.library)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.env=patch.dict(os.environ,PEARL_DISPATCH_LIBRARY=str(self.library));self.env.start()
        self.session,self.job,self.message=synthetic_session(bytes(32));self.device=NativeDevice();self.searches=[]
        base=prepare_base(self.job,self.session.is_current);front=NonceCommitmentCache.build(self.job,self.session.is_current)
        self.context=prepare_cached_nonce(self.job,base,b'TESTWORK',bytes(8),self.session.is_current,front)
        self.b=JobBTables(self.device,self.context,self.session.is_current);self.geometry=JobGeometry(self.device,self.job,self.session.is_current,maps=True)
    def tearDown(self):
        self.device.after_launch=None;self.device.after_reset=None;self.device.after_snapshot=None
        for s in self.searches:s.close()
        self.b.close();self.geometry.close();self.session.close();self.env.stop()
        self.assertFalse(self.device.allocations);self.assertFalse(self.device.graphs);self.assertFalse(self.device.executables)
        if self.device.callback_error is not None:raise self.device.callback_error
    def search(self,mode,start=0,current=None):
        s=new_search(self.context,self.device,current or self.session.is_current,self.b,self.geometry,mode=mode,start=start)
        self.searches.append(s);return s
    def test_C_and_ctypes_ABI_sizes_and_invalid_call_rejection(self):
        lib=native_library(str(self.library))
        self.assertEqual(tuple(lib.ph_abi_size(i)for i in range(4)),tuple(C.sizeof(k)for k in(Api,Call,KernelParams,MemsetParams)))
        call=Call();api=Api();self.assertEqual(lib.ph_dispatch(0,C.byref(api),C.byref(call)),-2);self.assertEqual(call.phase,0)
    def test_each_mode_retains_guards_and_reads_one_snapshot_per_window(self):
        for mode in MODES:
            with self.search(mode,start=5)as s:
                d=s.backend.dispatch;self.device.reads.clear();before=tuple(self.device.allocations)
                for amount in(5,7):
                    hit,cursor=s.advance(amount);self.assertIsNone(hit)
                self.assertEqual(cursor.next_tile,17);self.assertEqual(self.device.reads,[504,504]);self.assertEqual(tuple(self.device.allocations),before)
                if mode!='pair-direct':
                    expected=(2,4,2,2,0,0)if mode=='native-direct'else(0,0,2,2,4,2)
                    self.assertEqual(tuple(d.call.calls),expected);self.assertEqual(d.native_windows,2)
                    self.assertIsNone(d.prefetched)
    def test_graph_copies_and_refreshes_first_count_capacity_audit_generation(self):
        with self.search('native-graph',start=5)as s:
            d=s.backend.dispatch
            for first,count,capacity,audit,generation in((5,5,0,False,7),(32,1,1,True,(1<<63)+22),(1,7,7,False,8)):
                from tools.pair_depth_scan import Batch
                batch=Batch(s.plan,first,first+count)
                d.scan_window(batch,d.prepare_window(batch),generation,capacity=capacity,audit=audit)
                self.assertEqual(self.device.seen_scans[-1],(first,count,capacity,int(audit),generation))
    def test_all_28_guards_in_both_native_paths_fail_before_credit(self):
        retained=tuple(self.device.allocations)
        for mode in MODES[1:]:
            for index in range(28):
                s=self.search(mode);d=s.backend.dispatch;address=C.c_ulonglong(d.guard_addresses[index])
                d.upload(address,bytes(16))
                with self.assertRaisesRegex(RuntimeError,'guard'):s.advance(1)
                self.assertEqual(s.cursor.next_tile,0);self.assertTrue(s.closed)
                restore_retained_guard(self.device,self.b,self.geometry,address)
                self.assertEqual(tuple(self.device.allocations),retained)
    def test_stale_after_reset_never_decodes_or_credits_and_drains(self):
        for mode in MODES[1:]:
            valid=[True];s=self.search(mode,current=lambda job:valid[0]);self.device.after_reset=lambda:valid.__setitem__(0,False)
            with self.assertRaisesRegex(RuntimeError,'stale|no longer current'):s.advance(1)
            self.device.after_reset=None;self.assertTrue(s.closed);self.assertEqual(s.cursor.next_tile,0)
            self.assertFalse(self.geometry.leased);self.assertFalse(self.b.leased)
    def test_every_native_error_phase_is_reported_and_cleanup_preserves_shared_inputs(self):
        for mode in MODES[1:]:
            stages=(('cuMemsetD32Async',1,1),('cuLaunchKernel',1,2),('cuLaunchKernel',2,3),('cuStreamSynchronize',1,4),('cuMemcpyDtoH_v2',1,5))if mode=='native-direct'else(
                ('cuGraphExecKernelNodeSetParams',1,1),('cuGraphExecKernelNodeSetParams',2,2),('cuGraphLaunch',1,3),('cuStreamSynchronize',1,4),('cuMemcpyDtoH_v2',1,5))
            for name,occurrence,phase in stages:
                s=self.search(mode);self.device.native_occurrences.clear();self.device.error_native=(name,occurrence)
                with self.assertRaisesRegex(RuntimeError,'phase '+str(phase)+': CUDA error 777'):s.advance(1)
                self.device.error_native=None;self.assertTrue(s.closed);self.assertEqual(s.cursor.next_tile,0)
                self.assertFalse(self.geometry.leased);self.assertFalse(self.b.leased)
    def test_graph_creation_failure_destroys_partial_graph_and_releases_nonce(self):
        retained=tuple(self.device.allocations)
        for name in('cuGraphAddMemsetNode','cuGraphAddKernelNode','cuGraphInstantiateWithFlags'):
            self.device.fail_graph=name
            with self.assertRaisesRegex(RuntimeError,'injected'):self.search('native-graph')
            self.device.fail_graph=None;self.assertEqual(tuple(self.device.allocations),retained)
            self.assertFalse(self.device.graphs);self.assertFalse(self.geometry.leased);self.assertFalse(self.b.leased)
    def test_native_candidate_queue_uses_unchanged_independent_CPU_verifier(self):
        for mode in MODES[1:]:
            with self.search(mode)as s:
                d=s.backend.dispatch
                def emit():
                    self.device.write_bytes(d.status[1].value,struct.pack('<2I',1,0))
                    self.device.write_bytes(d.queue[1].value,struct.pack('<3I',0,self.job.generation,0)+bytes(32))
                self.device.after_launch=emit
                with patch('tools.pair_depth_scan.global_reference',return_value=[(bytes(64),bytes(32))])as ref:
                    hit,cursor=s.advance(1);self.assertIsNotNone(hit);ref.assert_called_once()
                self.device.after_launch=None
    def test_full_16K_overflow_retries_and_verifies_every_record(self):
        with patch('tools.check_prepared_job.MiningProfile',side_effect=lambda m,n,k,r,rows,cols:MiningProfile(160,16384,k,r,rows,cols)):
            session,job,_=synthetic_session(bytes(32))
        b=geometry=None
        try:
            base=prepare_base(job,session.is_current);front=NonceCommitmentCache.build(job,session.is_current)
            context=prepare_cached_nonce(job,base,b'TESTWORK',bytes(8),session.is_current,front)
            b=JobBTables(self.device,context,session.is_current);geometry=JobGeometry(self.device,job,session.is_current,maps=True)
            for mode in MODES[1:]:
                with new_search(context,self.device,session.is_current,b,geometry,mode=mode)as s:
                    d=s.backend.dispatch
                    def emit():
                        cap=d.queue_capacity.value
                        self.device.write_bytes(d.status[1].value,struct.pack('<2I',16384,int(cap<16384)))
                        self.device.write_bytes(d.queue[1].value,b''.join(struct.pack('<3I',i,job.generation,0)+bytes(32)for i in range(min(16384,cap))))
                    self.device.after_launch=emit
                    with patch('tools.pair_depth_scan.global_reference',return_value=[(bytes(64),bytes(32))])as ref:
                        hit,cursor=s.advance(16384)
                    self.assertEqual((cursor.next_tile,cursor.retries,hit.tile),(16384,1,0));self.assertEqual(ref.call_count,16384)
                    self.device.after_launch=None
                from tools import compare_dispatch
                with new_search(context,self.device,session.is_current,b,geometry,mode=mode)as s,patch.object(compare_dispatch,'WINDOW',16384):
                    report=compare_dispatch.diagnostic(s)
                    self.assertEqual(report['native_snapshot_bytes'],504)
                    self.assertEqual(report['native_driver_calls']['snapshot_copy'],1)
                    self.assertEqual(report['calls'].get('cuLaunchKernel',0),0)
        finally:
            if geometry is not None:geometry.close()
            if b is not None:b.close()
            session.close()

if __name__=='__main__':unittest.main()
