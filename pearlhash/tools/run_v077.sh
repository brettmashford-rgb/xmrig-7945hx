#!/usr/bin/env bash
printf 'Starting v77 register-pressure correctness, speed, power and bounded live tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.77 ]; then
    printf 'v77 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v077-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v077-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/6e3b403d803d8fd8248c3c1f8e450204316c4f5c/pearlhash/tools/install_v077.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='8718803f93bf6713290cf63cb50121d0f413dd827b7bf2a8260abd52bf9dc59c'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v77 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v077-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v77 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v077-launch.log
