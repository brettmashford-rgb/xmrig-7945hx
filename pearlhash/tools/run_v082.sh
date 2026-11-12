#!/usr/bin/env bash
printf 'Starting v82 two-nonce B-reuse correctness, speed and power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.82 ]; then
    printf 'v82 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v082-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v082-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/8b5c85af15715cd708c6e5442772a241ca3eb396/pearlhash/tools/install_v082.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='0ff0e46687ed61bfab21b3245419c459d9c7f8dcfbc321ca61df941df413345c'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v82 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v082-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v82 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v082-launch.log
