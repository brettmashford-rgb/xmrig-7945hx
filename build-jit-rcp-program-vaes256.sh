#!/bin/sh
# Separate source and output trees preserve the existing prefetch experiments.
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PIN=b2ca72480c58d197e18c885d9fc1a0c8d517e60a
JOBS=${JOBS:-2}
case "$JOBS" in ''|*[!0-9]*|0*) echo 'JOBS must be a positive integer' >&2; exit 2;; esac
[ "$#" -eq 0 ] || { echo 'Usage: sh build-jit-rcp-program-vaes256.sh' >&2; exit 2; }
[ -f /etc/alpine-release ] || { echo 'Run on Alpine Linux' >&2; exit 1; }
# Uses the verified baseline builder to install dependencies and obtain pinned source.
sh "$BASE/build-alpine.sh" 7168 generic
SOURCE="$BASE/.work/xmrig-jit-rcp-program-vaes256"
OUT="$BASE/.work/build-7168-jit-rcp-program-vaes256"
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
git -C "$REFERENCE" apply "$BASE/program-vaes256-only.patch"
git -C "$REFERENCE" diff HEAD > "$EXPECTED"
if git -C "$SOURCE" diff --quiet && git -C "$SOURCE" diff --cached --quiet; then
    git -C "$SOURCE" apply "$BASE/rcp-register-mask.patch"
    git -C "$SOURCE" apply "$BASE/program-vaes256-only.patch"
else
    ACTUAL=$(mktemp)
    git -C "$SOURCE" diff HEAD > "$ACTUAL"
    cmp -s "$ACTUAL" "$EXPECTED" || { rm -f "$ACTUAL"; echo 'Source has other changes; refusing to build.' >&2; exit 1; }
    rm -f "$ACTUAL"
fi
cmake -S "$SOURCE" -B "$OUT" -DCMAKE_BUILD_TYPE=Release -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DWITH_HWLOC=ON -DWITH_MSR=ON -DWITH_TLS=ON -DWITH_BENCHMARK=ON -DRX_AES_PREFETCH_DISTANCE=7168 -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$OUT" -j "$JOBS"
"$OUT/xmrig" --version
printf '\nExperimental RCP build with register-mask plus VAES-256 program generation: %s\n' "$OUT/xmrig"
printf 'Not started or installed. Compare checksum and performance before replacing the working miner.\n'
