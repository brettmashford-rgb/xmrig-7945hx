#!/usr/bin/env bash
printf 'Starting v76 wide16k scheduling correctness, speed and automatic GPU power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.76 ]; then
    printf 'v76 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v076-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v076-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/dd58e504e6f0aec1f692f41a3a7501906bcb8d80/pearlhash/tools/install_v076.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='31881219b2e1c25b34ae7158b22f6b5462c973a56ae0d263dcc5eda161c972b5'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v76 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v076-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=30m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v76 exit code: %s\n' "$rc"
    else
        printf '\nWildRig restart failed; 30-minute fallback retained.\n'
        rc=1
    fi
    rm -f "$installer"
    exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo systemctl stop pearl.service
sudo -u user -H timeout --signal=TERM --kill-after=15s 1500s \
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v076-launch.log
