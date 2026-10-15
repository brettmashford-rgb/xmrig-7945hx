# XMRig 7945HX AES prefetch experiment

Status: experimental tuning patch, NOT a proven hashrate upgrade.
Target: Ryzen 9 7945HX, Monero RandomX, diskless Linux, DDR5-5600.
User baseline: 17,300 H/s, 100 W at wall, 173 H/s/W.
Upstream inspected: xmrig/xmrig v6.26.0, commit b2ca724.

## What changed

The hardware-AES hash-and-fill routine had a fixed 7,168-byte software prefetch
look-ahead. This patch makes it a validated CMake build option. Default remains
7,168 bytes. Software AES and Zen 5's separate VAES512 routine are unchanged.
No hashing constants, RandomX instruction rules, wallet settings, developer
fee, MSR settings, or power settings are changed. No persistent background
service or pool connection is installed by these files.

Hypothesis: a different look-ahead may reduce stalls or cache pressure on the
7945HX. It could also make performance worse. Source inspection alone cannot
select a faster distance. No percentage improvement is claimed.

## Apply and build on a Linux build host

Requires git, CMake, a C/C++ compiler, and libuv, hwloc, OpenSSL development
packages appropriate to your distribution. Build for the target distribution
and libc; a dynamically linked glibc binary may not run on Alpine/musl.

```sh
git clone --branch v6.26.0 --depth 1 https://github.com/xmrig/xmrig.git xmrig-prefetch
cd xmrig-prefetch
git apply ../aes-prefetch.patch
cmake -S . -B build-7168 -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DRX_AES_PREFETCH_DISTANCE=7168
cmake --build build-7168 -j2
cmake -S . -B build-4096 -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DRX_AES_PREFETCH_DISTANCE=4096
cmake --build build-4096 -j2
cmake -S . -B build-2048 -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DRX_AES_PREFETCH_DISTANCE=2048
cmake --build build-2048 -j2
```

Keep identical compiler flags and dependencies for each build, and build one
variant at a time on a diskless machine to limit RAM usage. Other legal distances
are multiples of 256 between 256 and 8192 inclusive. Start with the three above;
the full range is not a recommendation to build every possible value.

The paths above assume this patch was placed beside the clone. Keep the original
miner executable available for immediate rollback. These are build instructions,
not commands to modify your boot image or existing running miner.

## Verification performed here

The changed AES translation unit compiled with g++ in C++11 mode. The hardware
AES routine was compared byte-for-byte with unmodified upstream using 4 input
patterns, scratchpad sizes 16 KiB, 256 KiB, 1 MiB and 2 MiB, and 3 chained rounds:
48 cases per variant. Hash, final fill state and complete scratchpad matched at
256, 1024, 2048, 4096, 6144, 7168 and 8192 bytes.
Invalid distances 0, 255, 257 and 8448 were rejected at compile time.
`git diff --check` passed.

Reproduce these component checks from this folder:

```sh
python3 verify.py /absolute/path/to/patched/xmrig-prefetch
```

The verification script expects HEAD to be the unmodified v6.26.0 source and
the working tree to contain the patch. It requires g++ and an x86 CPU with AES.
It compiles only the AES component; it is not a complete miner correctness test.

Full CMake configuration, complete miner linking, end-to-end RandomX benchmark
checksum and target power/hashrate tests were NOT performed here: CMake and
libuv/hwloc development packages are unavailable in this environment. The host
is a shared EPYC VM, not the user's 7945HX. CMake input validation is implemented
but was not executed here. No binary is supplied.

## Target acceptance test

First run the complete miner's built-in offline RandomX benchmark for rx/0 and
verify its final checksum before using any changed binary for live mining.
Keep config, thread affinity, MSR, huge pages, power limits and cooling identical.
Do not run benchmark variants concurrently. Allow temperatures and clocks to
settle; compare sustained hashrate with an external wall-power meter. Repeat
baseline and candidate runs in alternating order at least three times. Recheck
the winning candidate with a longer run and verify no new rejected/invalid shares.

At 100 W a candidate must consistently exceed the measured baseline, beyond
run-to-run noise. At higher power, it must maintain at least the baseline ratio:
required H/s = 173 * measured wall watts. For example, 110 W needs at least
19,030 H/s and 120 W needs at least 20,760 H/s. Re-measure the baseline under the
same conditions rather than assuming the original single reading is exact.

This first experiment is complete as a patch and component-verified. Choosing
an upgrade remains dependent on measurements from the actual mining hardware.
