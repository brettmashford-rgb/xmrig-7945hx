#!/usr/bin/env bash
printf 'Starting v75 combined Small4/16K correctness, speed and automatic GPU power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.75 ]; then
    printf 'v75 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v075-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v075-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/44a2876eb64124d3171f5f85614c26abb4fb0db8/pearlhash/tools/install_v075.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='4f046970f6ed8cc65bb1d412e5fc64e37d7dd9de2608f5f51e1b56723778aa8c'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v75 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v075-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=30m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v75 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v075-launch.log
