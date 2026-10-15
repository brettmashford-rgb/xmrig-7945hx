# XMRig 7945HX prefetch experiment for Alpine

Experimental tuning of XMRig v6.26.0. No measured speedup is claimed.
Baseline target: 17,300 H/s at 100 W at the wall (173 H/s/W).

The script downloads the official source at a fixed revision, applies the
included patch, then builds it on Alpine. It leaves the existing miner alone.

On your Alpine machine, run these first commands as root:

```sh
apk add --no-cache git ca-certificates
git clone https://github.com/brettmashford-rgb/xmrig-7945hx.git
cd xmrig-7945hx
sh build-alpine.sh 7168
sh build-alpine.sh 4096
sh build-alpine.sh 2048
```

Run from a directory containing the script and aes-prefetch.patch. As root, the
script installs build dependencies with apk. It builds with two jobs by default
to limit RAM use; override with JOBS=4 if desired. Packages come from your
existing Alpine repositories. Builds are dynamically linked for that Alpine
system, not promised portable to different releases.

Build outputs are .work/build-7168/xmrig, .work/build-4096/xmrig and
.work/build-2048/xmrig. The script prints versions but never starts mining,
changes autostart, runs lbu commit, or replaces the existing installation.
Diskless changes may disappear at reboot: choose a persistence location before
installing a winning build. Do not add the whole build tree to the boot backup.

Read EXPERIMENT.md for component test results and the full performance test plan.
The full miner build and script execution on Alpine are still unverified.
The build script passes sh syntax checking; compiler checks in verify.py cover
the changed AES component only. Validate the complete rx/0 benchmark checksum
before using a changed miner with a pool.

Upstream source and license: https://github.com/xmrig/xmrig/tree/v6.26.0
Official Alpine instructions: https://xmrig.com/docs/miner/build/alpine
The distributed patch is licensed under GPL-3.0-or-later, consistent with XMRig.
The upstream source download retains its original license notices. The original
build and verification scripts in this repository are also GPL-3.0-or-later.

## After building

Start with the 7168 build as the default-distance baseline. Use identical
settings for subsequent candidate comparisons. These commands perform an
offline rx/0 benchmark rather than connecting to a pool:

```sh
.work/build-7168/xmrig --bench=1M --algo=rx/0
.work/build-4096/xmrig --bench=1M --algo=rx/0
```

Confirm the miner reports a valid benchmark checksum. A short benchmark is a
correctness check, not sufficient proof of a sustained performance gain. Use
repeated longer comparisons with wall-power measurements for that decision.

Current verification: byte-for-byte AES component equivalence at seven
distances; shell syntax and invalid-argument checks. Full miner builds and
execution of this script on Alpine have not yet been verified.
