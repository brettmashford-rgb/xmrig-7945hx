#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_COMMIT=dfb5d4a5757a16e6f16c2088cae2e616e7b0dc66
BASE="https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/${SOURCE_COMMIT}/pearlhash"
FOLDER=/home/user/pearlhash-dev-v0.0.86-opencl
LOG=/home/user/pearlhash-v086-opencl.log

if [ -e "$FOLDER" ]; then
    printf 'OpenCL probe folder already exists; preserving it. Result log: %s\n' "$LOG"
    exit 1
fi
command -v curl >/dev/null || { echo 'curl is required.'; exit 1; }
command -v python3 >/dev/null || { echo 'python3 is required.'; exit 1; }
sudo -v
mkdir -p "$FOLDER/gpu" "$FOLDER/tools"
curl -fL --retry 3 "$BASE/gpu/opencl_tensor_core_probe.cl" -o "$FOLDER/gpu/opencl_tensor_core_probe.cl"
curl -fL --retry 3 "$BASE/tools/opencl_tensor_core_probe.py" -o "$FOLDER/tools/opencl_tensor_core_probe.py"
echo '991be2dffc968f4fee2ed8464e4f90f3dee4351cd69a01cfa046e1b1985971e4  '"$FOLDER/gpu/opencl_tensor_core_probe.cl" | sha256sum -c -
echo 'ae2479d3fe0ef386437d81b89bffc717432a12ed452f8a5150cc15a3555f310a  '"$FOLDER/tools/opencl_tensor_core_probe.py" | sha256sum -c -

fallback="pearl-v086-opencl-fallback-$(date +%s)-$$"
sudo systemd-run --unit="$fallback" --on-active=20m /usr/bin/systemctl start pearl.service
restore() {
    rc=$?
    trap - EXIT
    set +e
    if sudo systemctl start pearl.service && sudo systemctl is-active --quiet pearl.service; then
        sudo systemctl stop "$fallback.timer" >/dev/null 2>&1
        printf '\nWildRig restarted. OpenCL probe exit code: %s\n' "$rc"
    else
        printf '\nWildRig restart failed; 20-minute fallback retained.\n'
        rc=1
    fi
    exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo systemctl stop pearl.service
timeout --signal=TERM --kill-after=15s 900s python3 -S "$FOLDER/tools/opencl_tensor_core_probe.py" \
    --kernel "$FOLDER/gpu/opencl_tensor_core_probe.cl" --k 32768 --warps 512 --batches 8 --rounds 7 \
    2>&1 | tee "$LOG"
