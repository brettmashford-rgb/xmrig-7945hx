#!/usr/bin/env bash
printf 'Starting v85 pair-direct GPU hardware counters, baseline speed and power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.85 ]; then
    printf 'v85 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v085-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v085-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/7bb6bf8145c22914fe2f2a712c4c748b0b83ac22/pearlhash/tools/install_v085.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='1da445e3028d2f4c0717708b086986f842adf891dc4e5e2d82f3d8aae0af31aa'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v85 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v085-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v85 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v085-launch.log
