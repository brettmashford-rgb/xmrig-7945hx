# Fixed-size AVX2 Blake2b experiment

Retains register-mask and body-align32. The selected AVX2 Blake2b path already reads full 256-byte inputs directly; this experiment does not remove buffer copies. It adds a dedicated path for exactly 256 input bytes and 64 output bytes, used for the register-file digest between RandomX programs.

The specialised path uses the existing compression macros twice, with counters 128 and 256 and only the second block marked final. It fixes the unkeyed Blake2b-512 parameter word and writes both 32-byte output vectors directly. Other lengths and digest sizes retain the existing general implementation. The path remains inside the existing AVX2 dispatch, so no new CPU feature requirement is introduced.

This trades general loop/length/output handling for additional fixed-size code. Compression work is unchanged, and a target speed or power benefit is not established.

## Validation

- 5635 byte-for-byte comparisons with the independent scalar Blake2b reference: random and patterned fixed-size inputs, 32 input alignments, in-place output, output guards, and general inputs of every length from 0 through 512 with 16-, 32- and 64-byte digests.
- Production 250K rx/0 miner benchmark passed checksum `7D6054757BB08A63` on the separate Intel test host. Its timing is not a Ryzen prediction.
- Builder checks cover fresh and repeated builds, preservation of a dirty shared baseline, and refusal of unexpected experiment edits. Build-tool calls are mocked for isolation checks; the production miner is separately compiled and checksum-tested.

## Target run

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py blake-fixed
```

Defaults to 1M hashes, verifies `898B6E0431C28A6B`, and saves results without installing or starting a miner. Record H/s and wall watts. Optional long check: `python3 run-experiment.py blake-fixed --skip-build --bench 10M`.

Uses pinned upstream `b2ca72480c58d197e18c885d9fc1a0c8d517e60a`, existing `rcp-register-mask.patch`, and narrow `blake-fixed-only.patch`. Retains body alignment; excludes the preceding AES, direct-add, reciprocal-pool, phase, swap and branch-alignment experiments.
