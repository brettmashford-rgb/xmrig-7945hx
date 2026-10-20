#!/usr/bin/env python3
"""Switch an Alpine tmux miner to SupportXMR, optionally upgrading its binary."""
import argparse
import hashlib
import urllib.request
import datetime
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

POOL = 'pool.supportxmr.com:443'
VALUE_OPTIONS = {'-o', '--url', '-u', '--user', '-p', '--pass', '--rig-id',
                 '--tls-fingerprint', '--coin', '--algo', '-a', '--userpass', '-O'}
FLAG_OPTIONS = {'--nicehash', '--tls', '--keepalive', '-k'}


def parse_start(text):
    matches = []
    for index, line in enumerate(text.splitlines(keepends=True)):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        try:
            outer = shlex.split(line, comments=True)
        except ValueError:
            continue
        if outer and Path(outer[0]).name in ('xmrig', 'xmrig-miner'):
            # Older rigs launch directly with a log redirect and background '&'.
            command = re.sub(r'\s+>\s*/var/log/[A-Za-z0-9_.-]+\s+2>&1\s*&\s*$', '', line.strip())
            if command == line.strip():
                command = re.sub(r'\s*&\s*$', '', command)
            inner = shlex.split(command)
            if any(any(c in arg for c in (';', '|', '&', '>', '<', '`', '$')) for arg in inner):
                raise ValueError('Unsupported shell operators in the direct miner command.')
            session = 'xmrig'
            outer = ['tmux', 'new-session', '-d', '-s', session, command]
        elif len(outer) >= 6 and outer[:2] == ['tmux', 'new-session'] and '-s' in outer:
            session = outer[outer.index('-s') + 1]
            inner = shlex.split(outer[-1])
            if not inner or Path(inner[0]).name not in ('xmrig', 'xmrig-miner'):
                continue
            if outer.index('-s') + 2 != len(outer) - 1 or any(x in inner for x in ('&&', ';', '|', '&')):
                raise ValueError('Unsupported startup command; send the startup script for review.')
        else:
            continue
        matches.append((index, outer, inner, session))
    if len(matches) != 1:
        raise ValueError('Expected one recognised miner command in the startup script.')
    return matches[0]


def pool_args(inner):
    kept = [inner[0]]
    old_user = None
    old_pass = None
    old_pool = None
    i = 1
    while i < len(inner):
        arg = inner[i]
        key, eq, value = arg.partition('=')
        if key in VALUE_OPTIONS:
            if not eq:
                i += 1
                if i >= len(inner):
                    raise ValueError('Missing value for ' + key)
                value = inner[i]
            if key in ('-u', '--user'):
                old_user = value
            if key in ('-p', '--pass'):
                old_pass = value
            if key in ('-o', '--url'):
                old_pool = value
        elif key in FLAG_OPTIONS:
            pass
        else:
            kept.append(arg)
        i += 1
    worker = old_user.rsplit('.', 1)[1] if old_user and '.' in old_user else None
    if not worker and old_pool and 'pool.supportxmr.com' in old_pool and valid_worker(old_pass):
        worker = old_pass
    return kept, worker


def valid_worker(worker):
    return bool(worker and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', worker))


def rewrite(text, wallet, worker):
    index, outer, inner, session = parse_start(text)
    kept, _ = pool_args(inner)
    kept += ['-o', POOL, '--tls', '-a', 'rx/0', '-u', wallet, '-p', worker, '-k']
    outer[-1] = shlex.join(kept)
    lines = text.splitlines(keepends=True)
    lines[index] = shlex.join(outer) + '\n'
    return ''.join(lines), session


def miners_running():
    found = []
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            if (item / 'comm').read_text().strip() in ('xmrig', 'xmrig-miner'):
                found.append(item.name)
        except (OSError, UnicodeError):
            continue
    return found


def atomic_write(path, content):
    temp = path.with_name(path.name + '.pool-switch-tmp')
    try:
        temp.write_text(content)
        temp.chmod(path.stat().st_mode & 0o777)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def persistent_miner(text, executable):
    """Locate the persistent source of the startup copy without guessing names."""
    matches = []
    for line in text.splitlines():
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue
        if len(tokens) >= 3 and tokens[0] == 'cp' and tokens[-1] == executable:
            source = Path(tokens[-2])
            if source.parent == Path('/media/usb'):
                matches.append(source)
    if not matches and Path(executable).parent == Path('/media/usb'):
        matches.append(Path(executable))
    if len(matches) != 1 or not matches[0].is_file():
        raise ValueError('Cannot identify the persistent miner copy; no upgrade performed.')
    return matches[0]


def stage_miner(url, expected, destination):
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected or ''):
        raise ValueError('A SHA-256 digest is required for a miner upgrade.')
    if not url.startswith(('http://', 'https://')):
        raise ValueError('Miner URL must use http:// or https://.')
    temp = destination.with_name('.' + destination.name + '.upgrade-' + str(os.getpid()))
    try:
        digest = hashlib.sha256()
        count = 0
        with urllib.request.urlopen(url, timeout=30) as response, temp.open('xb') as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                if count > 64 * 1024 * 1024:
                    raise ValueError('Miner download exceeds 64 MiB.')
                digest.update(block)
                out.write(block)
        if digest.hexdigest() != expected.lower():
            raise ValueError('Miner SHA-256 mismatch; current miner was not changed.')
        temp.chmod(0o755)
        version = subprocess.run([str(temp), '--version'], check=True, timeout=15,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if 'XMRig' not in version.stdout:
            raise ValueError('Downloaded binary did not identify as XMRig.')
        print('Miner checksum and executable compatibility check passed.', flush=True)
        return temp
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def terminal_input(prompt):
    # Installer is delivered through a Python heredoc, so stdin is not the keyboard.
    with open('/dev/tty', 'r+') as tty:
        tty.write(prompt)
        tty.flush()
        answer = tty.readline()
    if not answer:
        raise ValueError('No terminal response; specify --worker or --wallet explicitly.')
    return answer.strip()


def stop_direct_miner(executable):
    stopped = False
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            target = os.readlink(item / 'exe').removesuffix(' (deleted)')
            if target == executable:
                os.kill(int(item.name), signal.SIGINT)
                stopped = True
        except (OSError, ValueError):
            continue
    return stopped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--wallet', help='Monero wallet; prompted if omitted')
    ap.add_argument('--worker', help='Worker name; inferred from old NiceHash username if possible')
    ap.add_argument('--miner-url', help='Optional replacement miner URL')
    ap.add_argument('--miner-sha256', help='Required SHA-256 for replacement miner')
    ap.add_argument('--dry-run', action='store_true', help='Show the planned startup script without changes')
    args = ap.parse_args()
    candidates = []
    for path in Path('/etc/local.d').glob('*.start'):
        text = path.read_text()
        if 'xmrig-miner' in text or 'xmrig' in text:
            candidates.append((path, text))
    if len(candidates) != 1:
        raise ValueError('Cannot identify one miner startup script. Run: cat /etc/local.d/*.start')
    start, original = candidates[0]
    _, _, inner, session = parse_start(original)
    _, inferred = pool_args(inner)
    wallet = args.wallet or terminal_input('Paste Monero wallet: ')
    if not re.fullmatch(r'[48][1-9A-HJ-NP-Za-km-z]{94}|[48][1-9A-HJ-NP-Za-km-z]{105}', wallet):
        raise ValueError('Wallet format is not a recognised mainnet Monero address.')
    worker = args.worker or inferred
    if not valid_worker(worker):
        worker = terminal_input('Worker name (e.g. 3900x or 5900x-2): ')
    if not valid_worker(worker):
        raise ValueError('Use letters, digits, underscores or hyphens for the worker name.')
    updated, session = rewrite(original, wallet, worker)
    print('Pool:', POOL, '(TLS)\nWorker:', worker, '\nStartup:', start)
    if args.miner_url:
        persistent = persistent_miner(original, inner[0])
        if not re.fullmatch(r'[0-9a-fA-F]{64}', args.miner_sha256 or ''):
            raise ValueError('Supply --miner-sha256 for the replacement binary.')
        print('Miner upgrade destination:', persistent, '(CPU settings retained)')
    else:
        persistent = None
        print('Existing miner binary and CPU settings retained.')
    if args.dry_run:
        print(updated)
        return
    if os.geteuid() != 0:
        raise ValueError('Run as root.')
    if not os.path.ismount('/media/usb'):
        raise ValueError('/media/usb is not mounted; no changes made.')
    if os.statvfs('/media/usb').f_flag & os.ST_RDONLY:
        subprocess.run(['mount', '-o', 'remount,rw', '/media/usb'], check=True)
    for tool in ('tmux', 'lbu', 'sh'):
        if not shutil.which(tool):
            raise ValueError('Missing tool: ' + tool)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = Path('/media/usb') / (start.name + '.before-supportxmr-' + stamp)
    shutil.copy2(start, backup)
    print('Backup:', backup, flush=True)
    staged = stage_miner(args.miner_url, args.miner_sha256, persistent) if persistent else None
    binary_backup = None
    if persistent:
        binary_backup = persistent.with_name(persistent.name + '.before-upgrade-' + stamp)
        shutil.copy2(persistent, binary_backup)
        print('Miner backup:', binary_backup, flush=True)
    active = subprocess.run(['tmux', 'has-session', '-t', '=' + session],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    was_running = active
    if active:
        subprocess.run(['tmux', 'send-keys', '-t', session + ':', 'C-c'], check=True)
    else:
        was_running = stop_direct_miner(inner[0])
    for _ in range(50):
        if not miners_running():
            break
        time.sleep(0.2)
    else:
        raise ValueError('A miner is still running; startup settings have not been changed.')
    # Wait for tmux to release the old session before starting its replacement.
    for _ in range(25):
        if subprocess.run(['tmux', 'has-session', '-t', '=' + session],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            break
        time.sleep(0.2)
    else:
        raise ValueError('Old tmux session remains; startup settings have not been changed.')
    try:
        if staged:
            os.replace(staged, persistent)
        atomic_write(start, updated)
        subprocess.run(['lbu', 'commit'], check=True)
    except Exception:
        if binary_backup:
            restore = persistent.with_name('.' + persistent.name + '.restore-' + str(os.getpid()))
            shutil.copy2(binary_backup, restore)
            os.replace(restore, persistent)
        atomic_write(start, original)
        subprocess.run(['lbu', 'commit'], check=False)
        if was_running:
            subprocess.run(['sh', str(start)], check=False)
        print('Startup settings restored from backup.', file=sys.stderr)
        raise
    os.sync()
    subprocess.run(['sh', str(start)], check=True)
    print('Saved for reboot and started. Checking miner output...', flush=True)
    time.sleep(5)
    subprocess.run(['tmux', 'capture-pane', '-p', '-t', session + ':', '-S', '-35'], check=True)
    print('Check for pool jobs and accepted shares.' + (' Miner binary upgraded.' if persistent else ' No miner binary was replaced.'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('STOP:', exc, file=sys.stderr)
        sys.exit(1)
