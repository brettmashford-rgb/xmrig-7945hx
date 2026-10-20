# AES hash/fill loop unrolling

Retains register-mask and body-align32. The hardware-AES fused hash/fill loop processes four cache lines (256 bytes) per iteration instead of two (128 bytes). The original two-line sequence is repeated within each loop iteration, retaining the order of AES updates and scratchpad reads/writes.

Every 64-byte cache line retains its prefetch hint, with the existing 7168-byte look-ahead. Software AES is unchanged. This halves loop iterations for the supported RandomX scratchpads, whose sizes and prefetch distance are multiples of 256. Larger loop code and register pressure may offset the reduced loop-control overhead; a target gain is not established.

## Validation

- Exact baseline/candidate hardware-AES function comparison: 40 cases across 8 KiB, 16 KiB, 64 KiB, 256 KiB and 2 MiB scratchpads. Final hashes, fill states and complete scratchpads matched.
- Compiled component inspection: two prefetch instructions in the original 128-byte loop, four in the new 256-byte loop.
- Production 250K rx/0 miner benchmark passed checksum `7D6054757BB08A63` on the separate Intel host. Its timing is not a Ryzen prediction.
- Builder checks cover fresh/repeated builds, preservation of a dirty shared baseline, and refusal of unexpected experiment edits. Build-tool calls are mocked for isolation checks; the production binary is separately compiled and checksum-tested.

## Run

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py aes-unroll256
```

Defaults to 1M hashes, verifies `898B6E0431C28A6B`, and saves results without installing or starting a miner. Record wall watts and H/s. Optional long check: `python3 run-experiment.py aes-unroll256 --skip-build --bench 10M`.

Uses pinned upstream `b2ca72480c58d197e18c885d9fc1a0c8d517e60a`, existing `rcp-register-mask.patch`, and narrow `aes-unroll256-only.patch`. The narrow patch retains body alignment and excludes prefetch thinning, direct-add, reciprocal pooling, phase shifting and swap/branch changes.
