#!/usr/bin/env python3
"""Validate compact stream queues against independent CPU cases. Offline. ISC."""
import argparse
import json
import os
from pathlib import Path
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.cached_a import CachedA,attach
from tools.stream_scan import StreamDispatch,execute_pair
from tools.prepared_dispatch import KERNELS
from tools.production_scan import ProductionCandidateScanner
from tools.virtual_scan import VirtualTables,global_reference
from tools.check_production_gpu import cases
from tools.check_warp_gpu import expected_transcripts
from tools.check_tile_scan_gpu import MAX_BOUND


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report={'complete':False,'error':None,'cases':[],'pool_connection':False,'submitted_shares':0}
    device=tables=cache=None;lanes=[]
    def clear():
        nonlocal tables,cache,lanes
        for lane in lanes:lane.wait()
        for resource in [*lanes,cache,tables]:
            if resource is not None:resource.close()
        lanes=[];cache=tables=None
    try:
        device=ProductionCandidateScanner();device.start(args.module)
        for name,profile,unique,_ in cases():
            refs=dict(zip(unique,global_reference(profile,unique)))
            queries=tuple(unique[i%len(unique)]for i in range(67));equal=[int.from_bytes(refs[q][1],'little')for q in queries]
            mixed=[v if i%2==0 else max(0,v-1)for i,v in enumerate(equal)]
            tables=VirtualTables(device,profile);cache=CachedA(tables);readbacks=[[],[]]
            for index in range(2):
                lane=StreamDispatch(device,tables,KERNELS[0]);lanes.append(lane);attach(lane,cache)
                original=lane.download
                def download(buffer,size,*,lane=lane,original=original,index=index):
                    if buffer is lane.queue:readbacks[index].append(size)
                    return original(buffer,size)
                lane.download=download
            for label,bounds,capacity in (('hit',[MAX_BOUND]*67,67),('miss',[0]*67,67),('equality',equal,67),
                    ('zero-queue',[MAX_BOUND]*67,0),('overflow',mixed,1),('mixed',mixed,67)):
                prepared=tuple(lane.prepare(queries,bounds)for lane in lanes);before=device.verified_tiles
                results=execute_pair(lanes,prepared,(1<<63)+44,True,capacity=capacity,audit=True)
                expected={i:refs[q][1]for i,q in enumerate(queries)if int.from_bytes(refs[q][1],'little')<=bounds[i]}
                for index,(result,traces)in enumerate(results):
                    if (result.total!=len(expected)or result.overflow!=(len(expected)>capacity)
                            or traces!=expected_transcripts(refs,queries)
                            or readbacks[index][-1]!=min(len(expected),capacity)*44):
                        raise RuntimeError('compact count/transcript/readback-size mismatch')
                    if result.overflow:
                        if len(result.records)!=capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                            raise RuntimeError('compact partial queue mismatch')
                    elif result.records!=expected:raise RuntimeError('compact complete candidate set mismatch')
                if results[0][0].overflow and device.verified_tiles!=before:raise RuntimeError('partial queue credited')
                report['cases'].append({'profile':name,'case':label,'passed':True})
            clear();print('PASS: compact queues:',name,'six CPU cases in both streams; exact populated read lengths.',flush=True)
        if device.allocations:raise RuntimeError('compact queue checks leaked allocations')
        report['complete']=True
    except (OSError,ValueError,RuntimeError)as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        try:clear()
        except Exception as exc:report['error']=report['error']or('cleanup: '+str(exc))
        if device is not None:
            try:device.close()
            except Exception as exc:report['error']=report['error']or('context cleanup: '+str(exc))
        report['complete']=report['complete']and report['error']is None
        with os.fdopen(fd,'w')as output:json.dump(report,output,indent=2);output.write('\n')
    if report['error']:print('STOP:',report['error'],flush=True);return 1
    print('QUEUE CHECKS: 18 CPU cases passed in both streams, including empty, full and overflowing queues.',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
