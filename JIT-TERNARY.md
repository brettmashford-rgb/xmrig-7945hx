# Zen 4 JIT division-mask experiment

This is a source rewrite of the generated RandomX execution loop, not a miner setting. It is experimental; no mining speed or power improvement has yet been established.

`h_FDIV_M` currently emits `andpd xmm12,xmm13` followed by `orpd xmm12,xmm14`. For Zen 4 with AVX512F, OS vector-state support and AVX512VL, this patch emits:

```asm
vpternlogq xmm12, xmm13, xmm14, 0xea
```

The exact operation is `(xmm12 & xmm13) | xmm14`. This replaces two instructions/eight code bytes with one instruction/seven bytes. It uses 128-bit registers. The subsequent division, address generation, rounding mode and RandomX parameters are unchanged. Other CPUs keep their existing path. Branch offsets remain generated from actual byte positions. The instruction clears the upper vector bits of xmm12's parent register; RandomX uses only its low 128 bits.

The hypothesis is reduced mask work/dependency length. This is a small part of RandomX and could be neutral or slower once execution resources, instruction placement and the complete workload are considered. Do not assume that halving this one instruction pair halves division cost or gives a particular hashrate gain.

## Build on Alpine

From the repository directory:

```sh
git pull --ff-only
sh build-jit-ternary.sh
```

The script first checks/builds the generic 7168 baseline and then builds a separate, pinned source tree. Output: `.work/build-7168-jit-ternary/xmrig`. Generic compiler flags, AES prefetch 7168, no LTO, same features as baseline. It does not install, start or replace the pool miner.

With other miners stopped, compare:

```sh
./.work/build-7168-jit-ternary/xmrig --bench=1M --algo=rx/0
```

The final 1M checksum must exactly match the baseline. Press Ctrl+C after the benchmark finishes. Record wall power and hashrate. Only if checksum passes and preliminary performance warrants it, use alternating longer baseline/candidate runs with the same seed, thread configuration and thermal conditions. A short run alone cannot establish a small speed improvement. Reboot persistence on diskless Alpine remains a separate backup step.

## Validation performed before publication

- Original and modified full JIT translation units compile with GCC 13.3, C++11, Linux x86-64.
- `git apply --check` and exact combined-diff comparison against the pinned upstream tree pass. Shell syntax check passes.
- `verify-jit-ternary.py` extracts the actual patched FDIV_M emitter and its address generator, then executes generated machine-code blocks against the unchanged fallback on an AVX512F/VL-enabled AMD EPYC host.
- 196,608 comparisons cover all eight source and destination register indices, four address modes, six immediates including signed/wraparound boundaries, 32 random input sets each and all four rounding modes. All output floating-point bits and MXCSR flags match.
- The modified whole miner has NOT been built here: full build dependencies are unavailable. This is NOT a full RandomX hash/consensus test. Alpine linking and the end-to-end hash checksum must still be verified on the target machine.
- No target 7945HX benchmark has been run for this patch.

Reproduce component verification after building, on a machine supporting AVX512F/VL:

```sh
python3 verify-jit-ternary.py .work/xmrig-jit-ternary
```

Instruction reference: Intel Architecture Instruction Set Extensions Programming Reference, VPTERNLOGQ, https://www.intel.com/content/dam/develop/external/us/en/documents/319433-024-697869.pdf . The original copyright and licence notices remain in the patched source files.

## Target results, 17 October 2026

Alpine GCC 15.2 full build succeeded. The target 1M result was 17,477.9 H/s at 96 W, with a matching checksum. Two subsequent JIT 10M runs were 17,395.1 H/s and approximately 17,341 H/s, bracketing an intervening baseline of 17,360.4 H/s. The 10M checksums matched. No repeatable speed improvement was established; this experiment is not the selected baseline.
