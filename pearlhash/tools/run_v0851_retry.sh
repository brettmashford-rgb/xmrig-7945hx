#!/usr/bin/env bash
printf 'Retrying V85 tensor-core counters with the compact Nsight CLI...\n'
if [ -e /home/user/pearlhash-dev-v0.0.85.1 ]; then
    printf 'V85.1 retry already started. Latest result:\n'
    tail -n 16 /home/user/pearlhash-v085.1-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v0851-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/57f1abe00e831e94f8e3a88994b01a83d255690b/pearlhash/tools/retry_v085_counters.py'
with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(1048577)
expected='f5a3cdd03139fea7a89f41682d2214ed2a9eaace343015f2253fa757b53882d3'
if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit('STOP: V85.1 retry checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('V85.1 pinned retry checksum verified.',flush=True)
PY
fallback="pearl-v0851-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. V85.1 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v085.1-launch.log
