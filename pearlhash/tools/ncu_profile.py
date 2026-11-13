"""Pinned private Nsight Compute extraction and literal counter reporting. ISC."""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import tarfile
import tempfile
from pathlib import PurePosixPath
import sys
import time
import urllib.request
URL='https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/nsight-compute-2025.4.1_2025.4.1.2-1_amd64.deb'
SIZE=322492696
SHA256='6aacf98f3c55226cf445975d348c297c1c7f785467397c9654cb26307a734d96'
SECTIONS=('SpeedOfLight','ComputeWorkloadAnalysis','SchedulerStats','WarpStateStats','InstructionStats','MemoryWorkloadAnalysis','LaunchStats','Occupancy')


def bounded(command,*,env=None,timeout=300):
    # Kill the whole instrumented process group on timeout, including Python target.
    previous={}
    def interrupted(signum,frame):raise RuntimeError('profiler interrupted by signal '+str(signum))
    for signum in (signal.SIGTERM,signal.SIGINT):
        previous[signum]=signal.signal(signum,interrupted)
    try:
        with subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,start_new_session=True) as child:
            try:
                output,_=child.communicate(timeout=timeout)
                return child.returncode,output
            except BaseException as error:
                os.killpg(child.pid,signal.SIGTERM)
                try:output,_=child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL);output,_=child.communicate(timeout=5)
                if isinstance(error,subprocess.TimeoutExpired):
                    raise RuntimeError('profiler command timed out: '+output[-1200:]) from error
                raise
    finally:
        for signum,handler in previous.items():signal.signal(signum,handler)


def prepare(folder):
    existing=shutil.which('ncu')
    if existing:return Path(existing).resolve(),'existing PATH',None
    if not shutil.which('dpkg-deb'):raise RuntimeError('dpkg-deb unavailable for private profiler extraction')
    roots=[Path('/dev/shm'),Path('/run')]
    root=next((item for item in roots if item.is_dir() and shutil.disk_usage(item).free>=SIZE+180*1024*1024),None)
    if root is None:raise RuntimeError('need about 490 MiB free in /dev/shm or /run for temporary profiler files')
    if shutil.disk_usage(folder).free<40*1024*1024:raise RuntimeError('need 40 MiB persistent space for the small profiler report')
    temporary=Path(tempfile.mkdtemp(prefix='pearlhash-ncu-',dir=root));base=temporary/'profiler'
    binary=base/'opt/nvidia/nsight-compute/2025.4.1/ncu'
    archive=temporary/'nsight-compute.deb';digest=hashlib.sha256();total=0;started=time.monotonic();last=started
    print('Downloading NVIDIA profiler package into RAM: 322 MB; extracting ~100 MB of CLI files into RAM.',flush=True)
    try:
        with urllib.request.urlopen(URL,timeout=30) as source,archive.open('xb') as output:
            while True:
                block=source.read(1024*1024)
                if not block:break
                total+=len(block)
                if total>SIZE or time.monotonic()-started>300:raise RuntimeError('profiler download exceeded size/time bound')
                digest.update(block);output.write(block)
                if time.monotonic()-last>5:
                    print('Profiler download:',str(total//1000000)+' / 322 MB',flush=True);last=time.monotonic()
        if total!=SIZE or digest.hexdigest()!=SHA256:raise RuntimeError('NVIDIA profiler checksum mismatch')
        base.mkdir(mode=0o700,exist_ok=True)
        process=subprocess.Popen(['dpkg-deb','--fsys-tarfile',str(archive)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        prefix='opt/nvidia/nsight-compute/2025.4.1/'
        allowed=(prefix+'target/linux-desktop-glibc_2_11_3-x64/',prefix+'sections/')
        selected=set();expanded=0
        try:
            with tarfile.open(fileobj=process.stdout,mode='r|*') as package:
                for member in package:
                    name=member.name.removeprefix('./')
                    if name!=prefix+'ncu' and not name.startswith(allowed):continue
                    rel=PurePosixPath(name)
                    if rel.is_absolute() or any(part in ('','..') for part in rel.parts):
                        raise RuntimeError('unsafe path in NVIDIA profiler archive')
                    target=base.joinpath(*rel.parts)
                    if member.isdir():target.mkdir(mode=0o700,parents=True,exist_ok=True)
                    elif member.isfile():
                        expanded+=member.size
                        if expanded>160*1024*1024:raise RuntimeError('selected CLI extraction exceeded 160 MiB')
                        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        source_file=package.extractfile(member)
                        if source_file is None:raise RuntimeError('NVIDIA CLI file content missing')
                        with source_file,target.open('xb') as output:
                            shutil.copyfileobj(source_file,output,1024*1024)
                        target.chmod(0o700 if member.mode&0o111 else 0o600)
                        selected.add(name)
                    else:raise RuntimeError('unexpected link or special file in selected profiler paths')
            errors=process.stderr.read();code=process.wait(timeout=30)
            if code:raise RuntimeError('NVIDIA profiler archive extraction failed: '+errors.decode('utf-8','replace')[-1000:])
        except BaseException:
            process.kill();process.wait();raise
        needed={prefix+'ncu',prefix+'target/linux-desktop-glibc_2_11_3-x64/ncu'}
        if not needed.issubset(selected):raise RuntimeError('required NVIDIA Nsight CLI files missing')
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    if not binary.is_file():
        shutil.rmtree(temporary,ignore_errors=True)
        raise RuntimeError('extracted profiler entry point missing')
    return binary,'private NVIDIA 2025.4.1 CLI in RAM; package SHA256 '+SHA256,temporary


def cleanup(binary,temporary=None):
    if temporary is not None:shutil.rmtree(temporary,ignore_errors=True)


def parse_csv(raw,expected=3):
    lines=raw.splitlines();header=None
    for i,line in enumerate(lines):
        names=next(csv.reader([line]),[])
        if all(x in names for x in ('ID','Kernel Name','Metric Name','Metric Unit','Metric Value')):
            header=i;break
    if header is None:raise ValueError('profiler CSV has no raw metric header')
    groups={};seen=set()
    for row in csv.DictReader(io.StringIO('\n'.join(lines[header:]))):
        name=row.get('Metric Name');kernel=row.get('Kernel Name','')
        if not name or name=='Metric Name':continue
        if kernel!='a_pair_direct_scan' and not kernel.startswith('a_pair_direct_scan('):
            raise ValueError('CSV contains a different kernel')
        identity=row['ID'];key=(identity,name)
        if key in seen:raise ValueError('duplicate metric for one kernel launch')
        seen.add(key)
        value=row.get('Metric Value','');unit=row.get('Metric Unit','')
        try:number=float(value.replace(',',''))
        except (ValueError,AttributeError):continue
        if not math.isfinite(number):continue
        groups.setdefault(name,[]).append(dict(launch_id=identity,value=number,unit=unit))
    ids={row['launch_id'] for rows in groups.values() for row in rows}
    if len(ids)!=expected:raise ValueError('expected '+str(expected)+' profiled scanner launches, got '+str(len(ids)))
    result={}
    for name,rows in groups.items():
        if len(rows)!=expected or len({r['unit'] for r in rows})!=1:continue
        result[name]=dict(mean=statistics.mean(r['value'] for r in rows),unit=rows[0]['unit'],samples=rows)
    required=('gpu__time_duration.sum','sm__throughput.avg.pct_of_peak_sustained_elapsed',
              'dram__throughput.avg.pct_of_peak_sustained_elapsed',
              'sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active')
    if any(name not in result for name in required):raise ValueError('required duration/SM/DRAM counters missing or incomplete')
    return result


def compact(metrics):
    names=('sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active',
           'sm__inst_executed_pipe_tensor_op_imma.avg.pct_of_peak_sustained_elapsed',
           'sm__throughput.avg.pct_of_peak_sustained_elapsed','dram__throughput.avg.pct_of_peak_sustained_elapsed',
           'smsp__warps_eligible.avg.per_cycle_active','smsp__issue_active.avg.pct_of_peak_sustained_active',
           'sm__warps_active.avg.pct_of_peak_sustained_active','smsp__warps_active.avg.pct_of_peak_sustained_active')
    rows={k:dict(value=metrics[k]['mean'],unit=metrics[k]['unit']) for k in names if k in metrics}
    tensors={k:v for k,v in metrics.items() if 'pipe_tensor' in k and 'cycles_active' in k and 'pct_of_peak' in k}
    rows.update({k:dict(value=v['mean'],unit=v['unit']) for k,v in tensors.items()})
    stalls=sorted(((k,v) for k,v in metrics.items() if 'warp_issue_stalled_' in k and k.endswith('_per_warp_active.pct')),
                  key=lambda item:item[1]['mean'],reverse=True)
    return dict(counters=rows,top_warp_stalls=[dict(metric=k,value=v['mean'],unit=v['unit']) for k,v in stalls[:5]],
        note='Literal hardware counters averaged across three launches. Stall metrics are not additive wall-time fractions; replay affects timings/cache state. No bottleneck diagnosis inferred automatically.')


def collect(folder,binary,env,module,commitment):
    report=dict(available=False,error=None,profiled_launches=3,skipped_scanner_launches=8,
        clock_control='none',cache_control='none',replay='kernel',privilege='user',
        scope='offline synthetic tiny-target work; profiler timings excluded from speed/energy; no pool',sections=list(SECTIONS))
    try:
        code,version=bounded([str(binary),'--version'],env=env,timeout=30)
        report['version']=version.strip()
        if code:raise RuntimeError('profiler executable failed: '+version[-1000:])
        temporary_root=next((parent for parent in binary.parents if parent.name.startswith('pearlhash-ncu-')),None)
        report_root=temporary_root if temporary_root is not None else folder
        report_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        report_prefix=report_root/'pair-direct'
        command=[str(binary),'--config-file','off','--clock-control','none','--cache-control','none',
                 '--replay-mode','kernel','--kernel-name-base','function','--kernel-name','a_pair_direct_scan',
                 '--launch-skip','8','--launch-count','3','--force-overwrite','--export',str(report_prefix)]
        for section in SECTIONS:command+=['--section',section]
        command += [sys.executable,'-S',str(folder/'tools/profile_pair.py'),'--counter-target',
                    '--module',str(module),'--commitment-module',str(commitment),'--report',str(folder/'counter-target.json')]
        run_env=env.copy();run_env['LC_ALL']='C';run_env['HOME']=str(report_root/'profiler-home')
        if temporary_root is not None:run_env['TMPDIR']=str(temporary_root)
        Path(run_env['HOME']).mkdir(exist_ok=True)
        print('Profiling three scanner launches after eight warm-up windows...',flush=True)
        code,output=bounded(command,env=run_env,timeout=600)
        report['profiler_output_tail']=output[-6000:]
        if 'ERR_NVGPUCTRPERM' in output:
            print('GPU counters require elevated access; retrying this diagnostic with sudo.',flush=True)
            names=('HOME','TMPDIR','PYTHONPATH','PEARL_HASH_LIBRARY','PYTHONUNBUFFERED','LC_ALL')
            prefix=['sudo','-n','env']+[name+'='+run_env[name] for name in names if name in run_env]
            code,output=bounded(prefix+command,env=run_env,timeout=600)
            report['profiler_output_tail']=output[-6000:];report['privilege']='sudo diagnostic only'
        if code:raise RuntimeError('profiler failed (exit '+str(code)+'): '+output[-1400:])
        target=json.loads((folder/'counter-target.json').read_text())
        if target.get('complete') is not True or target.get('error') is not None or target.get('range')!=[4194304,4374528]:
            raise RuntimeError('profile target did not complete its exact work/guard checks')
        # Import through the same privilege when a root-created report is not user-readable.
        export=[str(binary),'--import',str(report_prefix)+'.ncu-rep','--page','raw','--csv','--print-units','base','--print-fp']
        if report['privilege']!='user':export=prefix+export
        code,csv_output=bounded(export,env=run_env,timeout=120)
        if code:raise RuntimeError('profiler report export failed: '+csv_output[-1000:])
        metrics=parse_csv(csv_output);report.update(available=True,metrics=metrics,compact=compact(metrics))
    except (OSError,ValueError,RuntimeError) as error:report['error']=str(error)
    return report
