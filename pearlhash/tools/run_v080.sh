#!/usr/bin/env bash
printf 'Starting v80 paired 2/4/8-step correctness, speed, power and bounded live tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.80 ]; then
    printf 'v80 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v080-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v080-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/b7c3e9d6e579b643862b11e1152081e9eceb9d26/pearlhash/tools/install_v080.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='57df0111b3fe3c6eeb966cdadd4f1b0f8e2f4975019cea1c5f2c38c7fda5c281'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v80 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v080-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v80 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v080-launch.log
