#!/usr/bin/env bash
printf 'Starting v63 offline proof checks and benchmark launcher...\n'
if [ -e /home/user/pearlhash-dev-v0.0.63 ]; then
    printf 'v63 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v063-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v063-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/bde33a9539d743b6ef9a27ff7557c1eec49b5e71/pearlhash/tools/install_v063.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='09359afa8690858faa834f6fbd4ceafc8e85fc85c6acc9a85f6915c3ae1e921a'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v63 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v063-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=15m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v63 exit code: %s\n' "$rc"
    else
        printf '\nWildRig restart failed; 15-minute fallback retained.\n'
        rc=1
    fi
    rm -f "$installer"
    exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo systemctl stop pearl.service
sudo -u user -H timeout --signal=TERM --kill-after=15s 780s \
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v063-launch.log
