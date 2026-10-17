# Experimental compact integer add emission

This build starts from the working RCP rewrite with the donation subsystem removed. It does not include the swap-move experiment.

For IADD_RS with shift zero and destination other than the special displacement register (virtual r5, physical r13), emit `add dst, src` (3 bytes) instead of `lea dst, [dst + src]` (4 bytes). Shifted operations and every displacement-register operation keep the original emitter. This also covers equal source/destination registers with unsigned 64-bit wraparound.

The VM does not expose x86 arithmetic flags. Every generated CBRANCH emits its own ADD and TEST before consuming flags; the shorter ADD therefore preserves RandomX semantics. The destination's registerUsage still points immediately after its emitted instruction. This patch saves one code byte in the eligible case; it is not a proven speed or power improvement.

## Build on Alpine

```sh
git pull --ff-only
sh build-jit-compact-add.sh
```

Source: `.work/xmrig-jit-rcp-compact-add`. Output: `.work/build-7168-jit-rcp-compact-add/xmrig`. Generic compiler settings, prefetch distance 7168, no LTO, and complete donation removal remain. The script does not start or stop miners, install a binary, or change startup. It refuses unrelated source edits and preserves the existing experiment directories.

## Target test

Stop the pool miner before benchmarking, then run:

```sh
.work/build-7168-jit-rcp-compact-add/xmrig --bench=1M --algo=rx/0
```

Expected checksum: `898B6E0431C28A6B`. Keep the installed RCP build unless a measured improvement justifies replacing it. Do not compare with another miner running simultaneously.

## Verification

The changed JIT emitter compiles with the existing full Linux miner's Release options and links into a complete CPU miner with TLS, HTTP/API and benchmark support. A native emitted-code harness checks all 64 source/destination pairs and four shift values, including the unchanged displacement path, using 1,024 patterns each (262,144 checks). Inputs include zero, all ones, high bits and pseudorandom values; the signed immediate case is exercised with 0x80000001. The complete miner passes the offline 250K rx/0 checksum `7D6054757BB08A63`. The combined patch is checked against the pinned clean upstream revision. Target Alpine HWLOC/MSR compilation and performance remain to be tested.
