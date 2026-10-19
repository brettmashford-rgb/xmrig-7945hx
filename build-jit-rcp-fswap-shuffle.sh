#!/bin/sh
# Separate source and output trees preserve the existing prefetch experiments.
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PIN=b2ca72480c58d197e18c885d9fc1a0c8d517e60a
JOBS=${JOBS:-2}
case "$JOBS" in ''|*[!0-9]*|0*) echo 'JOBS must be a positive integer' >&2; exit 2;; esac
[ "$#" -eq 0 ] || { echo 'Usage: sh build-jit-rcp-fswap-shuffle.sh' >&2; exit 2; }
[ -f /etc/alpine-release ] || { echo 'Run on Alpine Linux' >&2; exit 1; }
# Prepare dependencies without rebuilding or modifying the shared baseline working tree.
if [ "$(id -u)" -eq 0 ]; then
    apk add --no-cache git make cmake libstdc++ gcc g++ libuv-dev openssl-dev hwloc-dev linux-headers ca-certificates
fi
for tool in git cmake make gcc g++; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing dependency: $tool" >&2; exit 1; }
done
UPSTREAM="$BASE/.work/xmrig-v6.26.0"
if [ ! -e "$UPSTREAM" ]; then
    mkdir -p "$BASE/.work"
    git clone --depth 1 --branch v6.26.0 https://github.com/xmrig/xmrig.git "$UPSTREAM"
fi
[ "$(git -C "$UPSTREAM" rev-parse HEAD)" = "$PIN" ] || { echo 'Unexpected upstream revision; refusing to build.' >&2; exit 1; }
SOURCE="$BASE/.work/xmrig-jit-rcp-fswap-shuffle-r2"
OUT="$BASE/.work/build-7168-jit-rcp-fswap-shuffle-r2"
EXPECTED=$(mktemp)
REFERENCE=$(mktemp -d)
trap 'rm -f "$EXPECTED"; rm -rf "$REFERENCE"' EXIT HUP INT TERM
if [ ! -e "$SOURCE" ]; then
    # Clone locally without copying the working-tree AES patch.
    git clone --no-hardlinks "$BASE/.work/xmrig-v6.26.0" "$SOURCE"
fi
[ "$(git -C "$SOURCE" rev-parse HEAD)" = "$PIN" ] || { echo 'Unexpected JIT source revision' >&2; exit 1; }
# Construct expected source from the already-published baseline plus this narrow delta.
git clone --no-hardlinks "$BASE/.work/xmrig-v6.26.0" "$REFERENCE"
[ "$(git -C "$REFERENCE" rev-parse HEAD)" = "$PIN" ] || exit 1
git -C "$REFERENCE" apply "$BASE/rcp-register-mask.patch"
git -C "$REFERENCE" apply "$BASE/fswap-shuffle-only.patch"
git -C "$REFERENCE" diff HEAD > "$EXPECTED"
if git -C "$SOURCE" diff --quiet && git -C "$SOURCE" diff --cached --quiet; then
    git -C "$SOURCE" apply "$BASE/rcp-register-mask.patch"
    git -C "$SOURCE" apply "$BASE/fswap-shuffle-only.patch"
else
    ACTUAL=$(mktemp)
    git -C "$SOURCE" diff HEAD > "$ACTUAL"
    cmp -s "$ACTUAL" "$EXPECTED" || { rm -f "$ACTUAL"; echo "Unexpected changes in $SOURCE; refusing to build." >&2; exit 1; }
    rm -f "$ACTUAL"
fi
cmake -S "$SOURCE" -B "$OUT" -DCMAKE_BUILD_TYPE=Release -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DWITH_HWLOC=ON -DWITH_MSR=ON -DWITH_TLS=ON -DWITH_BENCHMARK=ON -DRX_AES_PREFETCH_DISTANCE=7168 -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$OUT" -j "$JOBS"
"$OUT/xmrig" --version
printf '\nExperimental RCP build with register-mask plus PSHUFD floating swaps: %s\n' "$OUT/xmrig"
printf 'Not started or installed. Compare checksum and performance before replacing the working miner.\n'
