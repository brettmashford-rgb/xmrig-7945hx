#!/bin/sh
# Build an experimental miner beside the existing installation; never install it.
set -eu
DISTANCE=${1:-7168}
JOBS=${JOBS:-2}
case "$DISTANCE" in ''|*[!0-9]*|0*) echo 'Distance must be an integer 256..8192 without leading zeros' >&2; exit 2;; esac
case "$JOBS" in ''|*[!0-9]*|0*) echo 'JOBS must be a positive integer without leading zeros' >&2; exit 2;; esac
[ "${#DISTANCE}" -le 4 ] && [ "$DISTANCE" -ge 256 ] && [ "$DISTANCE" -le 8192 ] && [ "$((DISTANCE % 256))" -eq 0 ] || { echo 'Distance must be 256..8192, multiple of 256' >&2; exit 2; }
[ -f /etc/alpine-release ] || { echo 'Run this script on Alpine Linux.' >&2; exit 1; }
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$BASE/aes-prefetch.patch" ] || { echo 'Missing aes-prefetch.patch beside script' >&2; exit 1; }
if [ "$(id -u)" -eq 0 ]; then
    apk add --no-cache git make cmake libstdc++ gcc g++ libuv-dev openssl-dev hwloc-dev linux-headers ca-certificates
else
    echo 'Before building, have root install: git make cmake libstdc++ gcc g++ libuv-dev openssl-dev hwloc-dev linux-headers ca-certificates'
fi
for tool in git cmake make gcc g++; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing dependency: $tool" >&2; exit 1; }
done
SOURCE="$BASE/.work/xmrig-v6.26.0"
PIN=b2ca72480c58d197e18c885d9fc1a0c8d517e60a
if [ ! -e "$SOURCE" ]; then
    mkdir -p "$BASE/.work"
    git clone --depth 1 --branch v6.26.0 https://github.com/xmrig/xmrig.git "$SOURCE"
fi
[ "$(git -C "$SOURCE" rev-parse HEAD)" = "$PIN" ] || { echo 'Unexpected upstream revision; refusing to modify it.' >&2; exit 1; }
if git -C "$SOURCE" diff --quiet && git -C "$SOURCE" diff --cached --quiet; then
    git -C "$SOURCE" apply --check "$BASE/aes-prefetch.patch"
    git -C "$SOURCE" apply "$BASE/aes-prefetch.patch"
else
    EXPECTED=$(mktemp)
    trap 'rm -f "$EXPECTED"' EXIT HUP INT TERM
    git -C "$SOURCE" diff HEAD > "$EXPECTED"
    cmp -s "$EXPECTED" "$BASE/aes-prefetch.patch" || { echo 'Source has other changes; refusing to build.' >&2; exit 1; }
    rm -f "$EXPECTED"
    trap - EXIT HUP INT TERM
fi
OUT="$BASE/.work/build-$DISTANCE"
cmake -S "$SOURCE" -B "$OUT" -DCMAKE_BUILD_TYPE=Release -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DWITH_HWLOC=ON -DWITH_MSR=ON -DWITH_TLS=ON -DWITH_BENCHMARK=ON -DRX_AES_PREFETCH_DISTANCE="$DISTANCE"
cmake --build "$OUT" -j "$JOBS"
"$OUT/xmrig" --version
printf '\nBuilt: %s\n' "$OUT/xmrig"
printf 'Experimental only. Run the rx/0 benchmark checksum test before mining.\n'
printf 'The miner has not been installed or started. Save selected files to your persistent media before reboot.\n'
