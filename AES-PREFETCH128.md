# Reduced AES prefetch frequency

Retains register-mask and body-align32. The hardware-AES fused hash/fill loop processes 128 bytes per iteration. This candidate removes its second cache-line prefetch, leaving one hint per 128 bytes instead of one per 64 bytes. The existing 7168-byte look-ahead is retained.

All hash/fill loads, stores, AES operations, buffer wrapping and software-AES paths are unchanged. This reduces prefetch instructions, but the skipped cache-line hint could increase stalls. Target performance and wall power decide whether it is useful.

## Validation

- Exact selected baseline and candidate hardware-AES functions were compared across 24 cases: eight inputs at 8 KiB, 64 KiB and 2 MiB. Final 64-byte hashes, final 64-byte fill states, and complete scratchpads matched.
- The compiled component contains two static prefetch instructions in the baseline and one in the candidate.
- Production 250K rx/0 miner benchmark passed expected checksum `7D6054757BB08A63` on the separate Intel test host. Host timing is not a Ryzen prediction.
- Builder isolation checks cover fresh and repeated builds, preservation of a dirty shared baseline, and refusal of unexpected experiment changes. Build-tool calls are mocked in these checks; the production binary is separately compiled and checksum-tested.

## Target run

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py aes-prefetch128
```

The runner defaults to 1M hashes and verifies `898B6E0431C28A6B`. It saves results without installing or starting a miner. Record wall watts as well as H/s. An optional longer check is `python3 run-experiment.py aes-prefetch128 --skip-build --bench 10M`.

The builder uses pinned upstream `b2ca72480c58d197e18c885d9fc1a0c8d517e60a`, the existing `rcp-register-mask.patch`, and narrow `aes-prefetch128-only.patch`. The narrow patch includes retained body alignment and excludes direct-add, reciprocal pooling, phase shifting, and swap/branch-alignment experiments.
