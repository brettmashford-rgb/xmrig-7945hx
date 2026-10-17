#!/usr/bin/env python3
"""Offline RandomX candidate screen: ABBA runs, automatic exit, checksum checks.
This is a development screen, not proof of target speed or power improvement.
Binaries must be built beforehand using matching compiler/build settings.
"""
import argparse, json, os, pathlib, re, selectors, signal, subprocess, time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=pathlib.Path)
parser.add_argument('candidate',type=pathlib.Path)
parser.add_argument('--threads',type=int,default=min(8,len(os.sched_getaffinity(0))))
parser.add_argument('--size',choices=['250K','500K','1M','10M'],default='250K')
parser.add_argument('--timeout',type=float,default=1800)
parser.add_argument('--output',type=pathlib.Path,required=True,help='New output directory; existing paths are refused')
args=parser.parse_args()
if args.threads<1 or args.timeout<=0:parser.error('threads and timeout must be positive')
paths={name:str(path.resolve(strict=True)) for name,path in [('baseline',args.baseline),('candidate',args.candidate)]}
args.output.mkdir(parents=True,exist_ok=False)
pattern=re.compile(r'benchmark finished in\s+([\d.]+) seconds\s+\(([\d.]+) h/s\) hash sum =\s*([0-9a-fA-F]+)',re.I)
ansi=re.compile(r'\x1b\[[0-9;]*m')
results=[]
# RX_0, default zero seed, from pinned v6.26.0 BenchState_test.h.
reference={'250K':'7D6054757BB08A63','500K':'96607546DE1F5ECC','1M':'898B6E0431C28A6B','10M':'B5231262E2792B26'}[args.size]
for number,name in enumerate(['baseline','candidate','candidate','baseline'],1):
    command=[paths[name],'--bench='+args.size,'--algo=rx/0','--threads='+str(args.threads),'--no-huge-pages','--no-color','--print-time=10']
    logfile=args.output/f'{number}-{name}.log'
    with logfile.open('w') as log:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        start=time.monotonic()
        result=None
        content=""
        selector=selectors.DefaultSelector()
        selector.register(process.stdout,selectors.EVENT_READ)
        try:
            while time.monotonic()-start<args.timeout:
                ready=selector.select(timeout=0.25)
                if ready:
                    chunk=os.read(process.stdout.fileno(),65536)
                    if not chunk:
                        if process.poll() is not None:break
                    else:
                        decoded=chunk.decode(errors='replace')
                        log.write(decoded);log.flush()
                        content=(content+ansi.sub('',decoded))[-8192:]
                match=pattern.search(content)
                if match:
                    result={'order':number,'label':name,'binary':paths[name],'seconds':float(match[1]),'hashrate':float(match[2]),'checksum':match[3].upper(),'command':command}
                    break
                if process.poll() is not None:break
        finally:
            selector.close()
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    if not result:raise SystemExit(f'{name} did not finish successfully; inspect {logfile}')
    if result['checksum']!=reference:raise SystemExit(f'CHECKSUM MISMATCH: inspect {logfile}; candidate is not valid')
    results.append(result)
    (args.output/'results.json').write_text(json.dumps({'threads':args.threads,'size':args.size,'runs':results},indent=2)+'\n')
    print(f"{number}: {name}: {result['hashrate']:.1f} H/s, checksum {result['checksum']}",flush=True)
means={name:sum(r['hashrate'] for r in results if r['label']==name)/2 for name in paths}
print(f"Baseline mean {means['baseline']:.1f} H/s; candidate mean {means['candidate']:.1f} H/s; difference {(means['candidate']/means['baseline']-1)*100:+.3f}%")
print('Screen only: shared-host variance, profiling and memory topology can obscure small effects. Target wall power is not measured.')
