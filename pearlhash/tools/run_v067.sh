#!/usr/bin/env bash
printf 'Starting v67 sequential transcript proof checks and offline comparison...\n'
if [ -e /home/user/pearlhash-dev-v0.0.67 ]; then
    printf 'v67 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v067-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v067-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/42d4b9c479c4d777c89eda1263c34e36cfae4353/pearlhash/tools/install_v067.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='9f911c93a9198f35c6318465c8b7712b5309296a679fc26127a08602ea4d30d3'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v67 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v067-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=15m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v67 exit code: %s\n' "$rc"
    else
        printf '\nWildRig restart failed; 15-minute fallback retained.\n'
        rc=1
    fi
    rm -f "$installer"
    exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo systemctl stop pearl.service
sudo -u user -H timeout --signal=TERM --kill-after=15s 780s \
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v067-launch.log
