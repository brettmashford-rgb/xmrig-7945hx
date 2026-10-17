# Reciprocal-multiply JIT experiment

This source rewrite changes how RandomX's constant reciprocal multiplications execute. The original JIT puts the first 16 reciprocal constants on the stack and emits a memory-operand multiply. This experiment emits the existing register-constant fallback for every reciprocal multiply:

```asm
movabs rax, reciprocal_constant
imul destination, rax
```

It removes repeated stack reads from those operations at the cost of more code bytes/instructions. It does not replace RandomX arithmetic with approximations. Zero/power-of-two handling and branch register-use tracking are unchanged. The prologue/stack layout remains unchanged; unused reciprocal slots remain present. It includes neither previous JIT rewrite. AES prefetch stays 7168, generic compiler flags and LTO off.

## Local full-miner screening

A full miner was built with the rewrite and compared with an otherwise-identical baseline on an AMD EPYC Zen 4 virtual host (GCC 13.3, eight workers, profiling enabled, huge pages off). The 250K benchmark was run in ABBA order:

| Order | Binary | H/s | Checksum |
|---|---|---:|---|
| 1 | Baseline | 3813.9 | 7D6054757BB08A63 |
| 2 | Reciprocal rewrite | 3870.7 | 7D6054757BB08A63 |
| 3 | Reciprocal rewrite | 3914.8 | 7D6054757BB08A63 |
| 4 | Baseline | 3853.3 | 7D6054757BB08A63 |

Means: baseline 3833.6 H/s, rewrite 3892.75 H/s, difference +1.543%. The checksum matches pinned upstream v6.26.0's RX_0 250K reference. These are full RandomX workload tests, not only instruction microbenchmarks.

This is a screening result, NOT an established target improvement. Two runs per build are not sufficient for statistical confidence on a shared host. A separate exploratory baseline run reached 3908.3 H/s, illustrating material run variation. The target uses different topology, Alpine GCC 15.2, MSR/huge pages and power constraints. Target observations are recorded below; attribution of a power improvement remains provisional. Correct hashes for the tested default-seed workload do not prove correctness for all inputs.

Build/link passed locally; patch application, canonical combined-diff and shell syntax checks pass. Dependent/independent instruction microbenchmarks alone had shown no clear advantage, which is why the full workload was tested. See `HOST-SCREENING.md` and `results/2026-10-17-host-rcp.json` for environment and raw run summaries.

## Alpine build

From the repository folder:

```sh
git pull --ff-only
sh build-jit-rcp.sh
```

The output is `.work/build-7168-jit-rcp/xmrig`. Source/output directories are separate from previous experiments. The script checks/builds baseline as needed but does not install, start or replace the pool miner.

First test, with other miners stopped:

```sh
./.work/build-7168-jit-rcp/xmrig --bench=1M --algo=rx/0
```

Its checksum must match the baseline 1M checksum. Note wall power and press Ctrl+C when finished. A longer controlled comparison is warranted only if target correctness and the short result justify it. Preserve files to persistent media before rebooting diskless Alpine.

## Ryzen 7945HX observations, 17 October 2026

The Alpine GCC 15.2 build succeeded. The first target run was 10M hashes (rather than the initially requested 1M): 574.618 seconds, 17,402.9 H/s, with the expected 10M checksum B5231262E2792B26. Wall power initially read 91 W and settled at 92 W. A second 10M run was reported at 93 W; its photo reads approximately 17.4 kH/s, but is too blurred to transcribe an exact rate reliably.

The existing 7168 baseline was 17,368.6 H/s at 96 W. Using that prior baseline gives approximately 3–4.5% better observed hashes per watt for the reciprocal candidate. These are provisional comparisons: the user declined another baseline run, and conditions were not controlled closely enough to attribute the power difference conclusively to the patch. Retain this as the leading candidate, not a proven performance claim. Do not repeat the declined baseline test.

The user reports saving the repository/builds to /media/usb/xmrig-7945hx-rcp-backup.tar.gz and running sync. This is a reported backup, not an independently validated restore test. Pool startup has not been switched by these build scripts.

## Follow-up source audit

The reciprocal constant setup still executes 16 movabs/push pairs followed by add rsp,128. Those slots are unused by this candidate's generated multiplies. The sequence executes once per program invocation, outside the RX_0 loop whose default iteration count is 2048. Removing it is a lower-priority candidate than changes to repeated loop work. No cleanup patch or additional target rebuild is proposed on that basis alone. Stack layout and dynamic eMask patch offsets must be preserved if this is revisited.
