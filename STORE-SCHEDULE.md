# Experimental scheduling of loop-store computations

This candidate uses the working RCP immediate-multiply rewrite with complete donation removal. It includes none of the swap-moves, compact-add or unused-setup-removal experiments.

In the rx/0 loop-store template, move the four register-only XORPD operations to the beginning of the template, before loading the integer-store pointer and issuing eight integer stores. The integer and floating memory stores retain their original order, addresses and data. Only the timing of the independent floating-register calculations changes. The intent is to expose those calculations earlier to overlap with integer-store work; no speed or power improvement is assumed. Total instruction count and emitted size remain unchanged. RandomX v2 AES store templates are unchanged.

## Build on Alpine

```sh
git pull --ff-only
sh build-jit-store-schedule.sh
```

Source: `.work/xmrig-jit-rcp-store-schedule`. Output: `.work/build-7168-jit-rcp-store-schedule/xmrig`. Generic flags, prefetch distance 7168, no LTO and donation removal remain. The script neither starts nor stops miners, installs a binary, nor changes startup. Unrelated source edits cause refusal.

Stop the pool miner before running:

```sh
.work/build-7168-jit-rcp-store-schedule/xmrig --bench=1M --algo=rx/0
```

Expected checksum: `898B6E0431C28A6B`. Record final hashrate and wall power. Keep the installed RCP build unless a measured improvement justifies replacement.

## Verification

The modified GNU assembly template compiles with the existing Linux CPU miner's Release options and links into the full TLS/HTTP/API/benchmark-enabled miner. Disassembly comparison verifies exactly the four XORPD instructions moved: all other instructions retain their order and operands. The complete miner passes offline 250K rx/0 checksum `7D6054757BB08A63`. The combined patch applies cleanly to the pinned upstream revision and reproduces the canonical diff. Target Alpine HWLOC/MSR compilation and performance remain to be tested. Windows/MASM has not been tested locally.
