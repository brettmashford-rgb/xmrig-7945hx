#!/usr/bin/env bash
printf 'Starting v84.1 exact noise projection, proof, full-nonce speed and power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.84.1 ]; then
    printf 'v84.1 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v084.1-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v084-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/634c1a878c4684e0bdd83c148be714610d2e676a/pearlhash/tools/install_v084_fix.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='c4f7cfd95660314f9be5e5c8508237589fdaee9c6e0c8c1aaaff11772f518313'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v84.1 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v084-fix-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v84.1 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v084.1-launch.log
