#!/usr/bin/env bash
printf 'Starting v81 2/4/8-column layout correctness, speed and power tests...\n'
if [ -e /home/user/pearlhash-dev-v0.0.81 ]; then
    printf 'v81 has already been started. Latest log output:\n'
    tail -n 16 /home/user/pearlhash-v081-launch.log 2>/dev/null || true
    exit 0
fi
set -Eeuo pipefail
sudo -v
installer=$(mktemp /tmp/pearl-v081-install.XXXXXX.py)
python3 - "$installer" <<'PY'
import hashlib,pathlib,sys,urllib.request
url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/69eef778ebfacfaf3244e1ae56d2f557fc30cd9a/pearlhash/tools/install_v081.py'
with urllib.request.urlopen(url,timeout=60) as response:
    raw=response.read(1048577)
expected='d5d497e5f856da7055c10e9397ee26802c95337df820b0fd74ac580166cc3306'
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP: installer checksum mismatch')
p=pathlib.Path(sys.argv[1]);p.write_bytes(raw);p.chmod(0o644)
print('v81 pinned installer checksum verified.',flush=True)
PY
fallback="pearl-v081-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=40m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. v81 exit code: %s\n' "$rc"
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
    python3 -S "$installer" 2>&1 | sudo -u user tee /home/user/pearlhash-v081-launch.log
