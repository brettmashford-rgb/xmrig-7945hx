#!/usr/bin/env bash
printf 'Starting v79 paired-column A-sharing correctness, speed and automatic power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.79 ]; then
    printf 'v79 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v079-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v079-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/4a71289cf347f4e1a8dca53a4a54574a4280666d/pearlhash/tools/install_v079.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='1e0ed4adef741876175f4d36c73422e28ef943b709f7b6ec67b18a9cd00dd8e0'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v79 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v079-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v79 exit code: %s\n' "$rc"
    else
        printf '\nWildRig restart failed; 40-minute fallback retained.\n'
        rc=1
    fi
    rm -f "$installer"
    exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo systemctl stop pearl.service
sudo -u user -H timeout --signal=TERM --kill-after=15s 2100s \
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v079-launch.log
