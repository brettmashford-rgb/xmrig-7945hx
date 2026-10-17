# Experimental integer swap emission

This experiment keeps the RCP immediate-multiply rewrite and complete donation removal, then changes only RandomX ISWAP_R emission. It is a candidate, not a confirmed performance improvement.

For different virtual registers, replace `xchg dst, src` with:

```asm
mov rax, dst
mov dst, src
mov src, rax
```

RAX is scratch between VM instructions. Both virtual registers retain their full 64-bit values; flags remain unchanged. Self swaps still emit no instructions. Both registerUsage entries point after the complete swap, preserving subsequent conditional-branch bookkeeping. The sequence grows from 3 to 9 bytes; any execution benefit must outweigh the extra instruction-fetch footprint. No CPU-specific speed claim is assumed.

## Build on Alpine

```sh
git pull --ff-only
sh build-jit-swap-moves.sh
```

The script uses separate `.work/xmrig-jit-rcp-swap-moves` and `.work/build-7168-jit-rcp-swap-moves` directories. It does not stop, start, install or overwrite the running pool miner. It uses generic compiler flags, AES prefetch distance 7168 and no LTO. The combined patch applies to the same pinned XMRig v6.26.0 revision as the existing experiments. Re-running requires an exact matching patch; unrelated source edits cause a refusal.

## Validate on the target

Stop the pool miner before benchmarking to avoid competing for CPU and memory. Do not run two miners together for a comparison.

```sh
.work/build-7168-jit-rcp-swap-moves/xmrig --bench=1M --algo=rx/0
```

Expected 1M checksum: `898B6E0431C28A6B`. A longer 10M check should produce `B5231262E2792B26`. Record wall power and final hashrate; keep the installed miner until an improvement is established. This builder makes no startup changes.

## Local verification

The changed JIT object was compiled with the existing full miner's Release options and linked into a full Linux CPU miner with TLS, HTTP/API and benchmarking. A native emitted-code harness exercised all 64 ordered register pairs with 1,024 input patterns each (65,536 checks), including zero, all-ones, high-bit patterns and pseudorandom values; register results and arithmetic flags matched. The full miner and the unchanged RCP build both passed an offline 250K rx/0 checksum check (`7D6054757BB08A63`). The target Alpine HWLOC/MSR build is still to be tested. The initial local timing screen was slower than the unchanged RCP build, so this remains a target-specific experiment and must not replace the installed miner without a measured improvement. This is not evidence of a speedup on Zen 4.
