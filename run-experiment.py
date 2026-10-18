#!/usr/bin/env python3
"""Build and checksum-test one reviewed experiment on the target miner."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
EXPERIMENTS = {
    'dataset-t0': ('build-jit-rcp-dataset-t0.sh', 'build-7168-jit-rcp-dataset-t0'),
    'early-once': ('build-jit-rcp-early-once.sh', 'build-7168-jit-rcp-early-once'),
    'early-dataset': ('build-jit-rcp-early-dataset.sh', 'build-7168-jit-rcp-early-dataset'),
    'fp-convert': ('build-jit-rcp-fp-convert.sh', 'build-7168-jit-rcp-fp-convert'),
    'round-nop': ('build-jit-rcp-round-nop.sh', 'build-7168-jit-rcp-round-nop'),
    'round-store': ('build-jit-rcp-round-store.sh', 'build-7168-jit-rcp-round-store'),
}
EXPECTED = '898B6E0431C28A6B'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
FINISHED = re.compile(r'benchmark finished in\s+([\d.]+) seconds\s+\(([\d.]+) h/s\)\s+hash sum =\s*([0-9a-fA-F]+)')


def active_miners():
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if (entry / 'comm').read_text().strip() in ('xmrig', 'xmrig-miner'):
                found.append(int(entry.name))
        except OSError:
            pass
    return found


def stop_child(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def capture(command, logfile, timeout, benchmark=False):
    """Stream output; interrupt only this child process group at completion."""
    proc = subprocess.Popen(command, cwd=BASE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True,
                            bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    pending = b''
    result = None
    complete = False
    try:
        with logfile.open('w') as log:
            while not complete:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Command exceeded its time limit')
                events = selector.select(timeout=0.25)
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        complete = True
                        break
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        clean = ANSI.sub('', line.decode('utf-8', errors='replace'))
                        print(clean, flush=True)
                        log.write(clean + '\n')
                        log.flush()
                        match = FINISHED.search(clean) if benchmark else None
                        if match:
                            result = {'seconds': float(match[1]),
                                      'hashrate_h_s': float(match[2]),
                                      'checksum': match[3].upper()}
                            complete = True
                            break
                    if complete:
                        break
            if pending:
                log.write(ANSI.sub('', pending.decode('utf-8', errors='replace')))
            if benchmark and result is not None:
                stop_child(proc)
            else:
                proc.wait(timeout=15)
            if proc.returncode not in (0, -signal.SIGINT, 128 + signal.SIGINT):
                raise RuntimeError('Command exited with status %s' % proc.returncode)
            if benchmark and result is None:
                raise RuntimeError('No completed benchmark result found')
            return result
    finally:
        selector.close()
        proc.stdout.close()
        stop_child(proc)


def result_folder():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for root in (Path('/media/usb/xmrig-test-results'), BASE / 'test-results'):
        try:
            if root.parent == Path('/media/usb') and not os.path.ismount('/media/usb'):
                continue
            folder = root / ('%s-%s' % (stamp, os.getpid()))
            folder.mkdir(parents=True, exist_ok=False)
            return folder
        except OSError:
            continue
    raise OSError('Cannot create a results folder')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment', nargs='?', choices=EXPERIMENTS, default='fp-convert')
    parser.add_argument('--skip-build', action='store_true', help='test the already-built binary')
    parser.add_argument('--watts', type=float, help='optional measured wall power')
    args = parser.parse_args()
    if args.watts is not None and (not 0 < args.watts < 100000):
        parser.error('--watts must be a positive finite reading')
    pids = active_miners()
    if pids:
        print('A miner is already running (PID %s). Stop it before testing.' % ', '.join(map(str, pids)))
        print('For the existing tmux pool miner: tmux send-keys -t xmrig C-c')
        return 2
    builder, directory = EXPERIMENTS[args.experiment]
    binary = BASE / '.work' / directory / 'xmrig'
    folder = result_folder()
    info = {'experiment': args.experiment, 'hashes': 1000000, 'algorithm': 'rx/0',
            'expected_checksum': EXPECTED, 'wall_watts': args.watts,
            'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': 'started'}
    code = 1
    try:
        if not args.skip_build:
            capture(['sh', str(BASE / builder)], folder / 'build.log', 3600)
        if not binary.is_file():
            raise RuntimeError('Build output is missing: %s' % binary)
        if active_miners():
            raise RuntimeError('Another miner started during the build; test cancelled')
        info.update(capture([str(binary), '--bench=1M', '--algo=rx/0'],
                            folder / 'benchmark.log', 900, benchmark=True))
        info['status'] = 'passed' if info['checksum'] == EXPECTED else 'checksum_failed'
        if args.watts is not None:
            info['hashes_per_joule'] = info['hashrate_h_s'] / args.watts
        code = 0 if info['status'] == 'passed' else 1
    except KeyboardInterrupt:
        info.update(status='interrupted', error='Interrupted by user')
        code = 130
    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        info.update(status='failed', error=str(exc))
    finally:
        info['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (folder / 'result.json').write_text(json.dumps(info, indent=2) + '\n')
        lines = ['Experiment: ' + args.experiment, 'Status: ' + info['status']]
        if 'hashrate_h_s' in info:
            lines += ['Hashrate: %.1f H/s' % info['hashrate_h_s'],
                      'Checksum: ' + info['checksum']]
        if args.watts is not None:
            lines.append('Wall power: %g W' % args.watts)
        if 'error' in info:
            lines.append('Error: ' + info['error'])
        (folder / 'summary.txt').write_text('\n'.join(lines) + '\n')
        os.sync()
        print('\n' + '\n'.join(lines))
        print('Results saved: ' + str(folder))
        print('No miner was installed or restarted. To resume the pool miner:')
        print('sh /etc/local.d/*.start')
    return code


if __name__ == '__main__':
    sys.exit(main())
