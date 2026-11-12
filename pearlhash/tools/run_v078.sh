#!/usr/bin/env bash
printf 'Starting v78 64-tile blocks, 16K/32K/64K dispatch correctness, speed and automatic power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.78 ]; then
    printf 'v78 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v078-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v078-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/901ff5f3edab1a06ef60740e67beff0d9256a7a0/pearlhash/tools/install_v078.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='b218632514d95b2b4599ab91e67dbf2f98792d222fa6f7dc98be06ab8204cf1b'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v78 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v078-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v78 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v078-launch.log
