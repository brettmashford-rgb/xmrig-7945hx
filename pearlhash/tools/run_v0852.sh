#!/usr/bin/env bash
printf 'Retrying V85 tensor-core counters with profiler files held in RAM...\n'
if [ -e /home/user/pearlhash-dev-v0.0.85.2 ]; then
    printf 'V85.2 retry already started. Latest result:\n'
    tail -n 16 /home/user/pearlhash-v085.2-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v0852-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/e99dbe27c1562b07e3869aa64b87ae7d5d4dd099/pearlhash/tools/retry_v0852_counters.py'
with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(1048577)
expected='bd880f8600f8c28a0faac52f9468d21f2f9c94dbcaad37abd0f33775abe014e9'
if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit('STOP: V85.2 retry checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('V85.2 pinned retry checksum verified.',flush=True)
PY
fallback="pearl-v0852-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. V85.2 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v085.2-launch.log
