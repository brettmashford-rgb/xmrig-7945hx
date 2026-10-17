# Zen 4 paired scratchpad-load experiment

This separate source experiment replaces the floating-point scratchpad-load portion of the generated RandomX loop. It does not include the earlier FDIV ternary-mask patch. AES prefetch distance stays 7168; generic compiler flags and LTO-off match the baseline.

## Rewrite

The original block converts eight pairs of signed 32-bit scratchpad integers to eight 128-bit floating-point registers, then applies eight mask instructions to the four E registers. The new block uses four 256-bit conversions, applies the masks in pairs and extracts the upper 128-bit halves into their required RandomX registers. The integer XOR loads and saved scratchpad pointers are unchanged.

This changes eight conversion instructions + eight mask instructions into four conversions + four extracts + two mask broadcasts + four masks. The resulting architectural low 128-bit register contents are identical. Upper vector halves and temporary xmm12 differ but are not RandomX VM state. Constants xmm13/xmm14 and the other live vector registers retain their low 128 bits. Loads do not widen beyond the same 64-byte region.

The generated template is 124 bytes. `jit-paired-load.inc` is its readable assembly; the verifier checks it assembles to exactly the bytes embedded in the JIT patch. `codePosFirst` uses the selected template's actual size, so subsequent branch positions are calculated correctly. Selection requires Zen 4 plus XMRig's OS-aware AVX/AVX2 checks. Other CPUs retain the original loader.

## Validation and limits

- Patched full JIT translation unit compiles with GCC 13.3, C++11 on Linux x86-64.
- 40,000 comparisons execute the actual embedded machine-code bytes against the original assembly, using four rounding modes, varied scratchpad offsets (including aliasing), signed integer extremes and random memory/masks. Integer registers, all eight output FP registers, other live vector-register low halves, saved scratchpad pointers, address inputs and MXCSR match exactly.
- Eight alternating local component-timing pairs on an AVX2-enabled AMD EPYC Zen 4 host showed the paired block consistently faster (roughly 1.4–1.5 ns versus 1.9–2.0 ns per repeated block in that run). These L1-resident component measurements are NOT whole-miner benchmarks and do not establish any hashrate improvement on the 7945HX.
- A 512-bit variant was also checked locally. Its outputs matched, but it was slower in the component benchmark and is not included.
- Full miner linking, end-to-end RandomX checksums, power and target performance remain to be checked on Alpine. Local full-miner dependencies are unavailable.
- Patch application, canonical combined-diff comparison and shell syntax checks pass.

## Build

From `/root/xmrig-7945hx`, enter separately:

```sh
git pull --ff-only
sh build-jit-paired-load.sh
```

Output: `.work/build-7168-jit-paired-load/xmrig`. The source and output trees are separate from baseline and the rejected division-mask experiment. The script does not replace or start the pool miner.

First target check, with the pool miner stopped:

```sh
./.work/build-7168-jit-paired-load/xmrig --bench=1M --algo=rx/0
```

Compare its checksum with the baseline before pool mining. Press Ctrl+C after completion. A speed difference needs matching longer runs before drawing conclusions. Reboot persistence on diskless Alpine still requires saving the new build to persistent media.

Reproduce local component verification:

```sh
python3 verify-jit-paired-load.py .work/xmrig-jit-paired-load
```

Append `--bench` for optional component timings. Requires Linux x86-64, AVX2/OS support, g++, GNU as and objcopy.

## Previous experiment status

The FDIV ternary-mask experiment passed target 1M and 10M checksum checks, but its two 10M runs (17,395.1 H/s and approximately 17,341 H/s) bracketed the intervening baseline (17,360.4 H/s). It did not establish a repeatable hashrate gain. This paired-load experiment starts from the baseline, not from that patch.
