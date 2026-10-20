# Direct unscaled addition experiment

Retains register-mask and body-align32. For IADD_RS with shift zero and a destination other than the VM register requiring an immediate displacement, emit `add r64, r64` instead of `lea r64, [base+index]`. This preserves the integer result while shortening the instruction from four bytes to three. Instruction count is unchanged; a performance gain is a hypothesis.

The r13 displacement case and shifted additions retain their original encodings. ADD changes native flags, which are not VM state; generated CBRANCH establishes its own flags immediately before its conditional jump. Code offsets and register-usage metadata follow the emitted instruction size.

## Validation

- 520 native differential VM executions against body-align32, 32 iterations each: complete register files, MXCSR, and complete 2 MiB scratchpads matched. Includes random mixed programs and additional integer-add programs covering all source/destination registers and shifts.
- Production 250K rx/0 benchmark passed checksum `7D6054757BB08A63` on the separate Intel test host. Host timing is not a Ryzen performance prediction.
- Builder checks cover fresh and repeated builds, preservation of a dirty shared baseline, and refusal of unexpected experiment edits. Build-tool calls are mocked in the isolation checks; the production binary is compiled and checksum-tested separately.

## Run

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py direct-add
```

Defaults to 1M hashes and validates checksum `898B6E0431C28A6B`. Results are saved; the miner is not installed or started. Record wall power as well as H/s. Optional long check: `python3 run-experiment.py direct-add --skip-build --bench 10M`.

Builds pinned upstream `b2ca72480c58d197e18c885d9fc1a0c8d517e60a` with the existing `rcp-register-mask.patch` and narrow `direct-add-only.patch`. The narrow delta retains body alignment and excludes reciprocal pooling, phase shifting, swap changes, and branch alignment.
