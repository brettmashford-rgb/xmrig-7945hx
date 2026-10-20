# Reciprocal constant pooling experiment

This experiment retains register-mask and body-align32. Each valid IMUL_RCP uses one `imul r64, [rip+disp32]` in place of `movabs rax, reciprocal; imul r64, rax`. The generated instruction sequence shrinks from 14 to 8 bytes and removes one instruction, while introducing a constant-table read. Performance and power on the target must be measured.

Only the existing register-mask path for 256-instruction full-memory programs selects the table. Other program sizes, light mode, XOP, and the existing V2 fallbacks retain immediate constants. Each program resets the table; zero and power-of-two divisors retain the existing no-op behavior.

The table starts at code offset 24576 and can hold all 256 reciprocals (2048 bytes), below the light-mode superscalar area at 32768 and separate from the fixed epilogue. Explicit bounds checks reject pool overflow or generated-code overlap. No class layout or allocation size changes are required.

## Validation

- Native differential execution against body-align32: 520 programs, 32 iterations each; complete register files, MXCSR, and complete 2 MiB scratchpads match. Includes random instruction streams, a full 256-entry table, zero/power-of-two divisors, and large divisors.
- Production miner 250K rx/0 benchmark: expected checksum `7D6054757BB08A63` passed on the separate Intel test host. Its timing is not a Ryzen performance prediction.
- Builder checks: fresh isolated source, repeat build, dirty shared baseline preservation, and refusal of unexpected experiment edits. Build-tool invocation is mocked for these isolation checks; the production binary is compiled and checksum-tested separately.

## Target run

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py rcp-pool
```

The runner defaults to 1M hashes, checks checksum `898B6E0431C28A6B`, saves results, and does not install or start the miner. Record wall power as well as H/s. A longer check uses `python3 run-experiment.py rcp-pool --skip-build --bench 10M`.

The builder uses pinned upstream `b2ca72480c58d197e18c885d9fc1a0c8d517e60a`, the existing `rcp-register-mask.patch`, and `rcp-pool-only.patch` in a separate source/output tree. The narrow patch includes retained body alignment and excludes prior phase, swap, and branch-alignment experiments.
