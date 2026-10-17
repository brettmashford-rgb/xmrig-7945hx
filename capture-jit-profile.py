#!/usr/bin/env python3
"""Capture a separate offline miner; never act on the pool miner."""
import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=15, choices=range(5, 31))
parser.add_argument('--threads', type=int, default=os.cpu_count())
args = parser.parse_args()
if not 1 <= args.threads <= 256:
    raise SystemExit('Invalid thread count')
binary = BASE / '.work/build-7168-jit-rcp-profile/xmrig'
if not binary.is_file():
    raise SystemExit('Build first: sh build-jit-profile.sh')
for comm in Path('/proc').glob('[0-9]*/comm'):
    try:
        if comm.read_text().strip() in ('xmrig-miner', 'xmrig'):
            raise SystemExit('A miner is running. Stop the pool miner before profiling.')
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
directory = BASE / ('profile-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
directory.mkdir()
env = dict(os.environ, RX_JIT_TRACE=str(directory / 'jit-trace.bin'))
command = ['perf', 'record', '-e', 'cycles:u', '-F', '499', '-k', 'mono', '-T',
           '-o', str(directory / 'perf.data'), '--', str(binary), '--bench=1M',
           '--algo=rx/0', '--threads=' + str(args.threads)]
print('Offline diagnostic capture:', directory, flush=True)
print('The pool miner must already be stopped. This script never changes startup.', flush=True)
with open(directory / 'capture.log', 'w') as log:
    process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
    try:
        process.wait(timeout=args.seconds)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
if not (directory / 'jit-trace.bin').is_file():
    raise SystemExit('No JIT trace captured. See ' + str(directory / 'capture.log'))
with open(directory / 'samples.txt', 'w') as samples:
    subprocess.run(['perf', 'script', '--ns', '-F', 'tid,time,ip', '-i',
                    str(directory / 'perf.data')], stdout=samples, check=True)
subprocess.run(['python3', str(BASE / 'report-jit-profile.py'), str(directory)], check=True)
print('Summary:', directory / 'summary.txt')
print('Machine-code examples:', directory / 'hot-examples.txt')
