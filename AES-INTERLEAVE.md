# Interleaved AES hash/fill scheduling

Retains register-mask and body-align32. The hardware-AES fused hash/fill loop changes from `hash(0), hash(1), fill(0), fill(1)` to `hash(0), fill(0), hash(1), fill(1)`. Each hash reads its cache line before fill overwrites it; the independent per-lane hash and fill state updates retain their order.

The loop still processes 128 bytes and retains both cache-line prefetch hints with the existing 7168-byte look-ahead. Software AES and all hashing constants are unchanged. The source schedule produces different machine code in the local component build, but no target speed or power benefit is established.

## Validation

- Exact baseline/candidate hardware-AES function comparison: 40 cases across 8 KiB, 16 KiB, 64 KiB, 256 KiB and 2 MiB scratchpads. Final hashes, fill states and complete scratchpads matched.
- Production 250K rx/0 miner benchmark passed expected checksum `7D6054757BB08A63` on the separate Intel host. Its timing is not a Ryzen prediction.
- Builder checks cover fresh and repeated builds, preservation of a dirty shared baseline, and refusal of unexpected experiment edits. Build-tool calls are mocked for isolation checks; the production miner is separately compiled and checksum-tested.

## Run

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py aes-interleave
```

Defaults to 1M hashes and verifies `898B6E0431C28A6B`. Saves results without installing or starting a miner. Record H/s and wall watts. Optional longer check: `python3 run-experiment.py aes-interleave --skip-build --bench 10M`.

Builds pinned upstream `b2ca72480c58d197e18c885d9fc1a0c8d517e60a`, existing `rcp-register-mask.patch`, and narrow `aes-interleave-only.patch`. The narrow delta retains body alignment and excludes 256-byte unrolling, prefetch thinning, direct-add, reciprocal pooling, phase shifting, and swap/branch-alignment experiments.
