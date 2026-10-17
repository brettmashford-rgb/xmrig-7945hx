# Timestamped JIT profiling for the working RCP build

This diagnostic build retains immediate-RCP multiplication, prefetch 7168 and full donation removal. None of the rejected swap, compact-add, setup-removal or store-scheduling candidates are included. It is not an optimisation candidate and must not replace the installed pool miner.

## Build

```sh
git pull --ff-only
sh build-jit-profile.sh
```

The script installs Python 3, binutils and perf on Alpine and builds a separate `.work/build-7168-jit-rcp-profile/xmrig`. It does not stop the pool miner, install the diagnostic binary, or change startup. This source tree enables WITH_JIT_TRACE and preserves native debug symbols. Generic Release optimisation flags otherwise remain. The exact patch is checked on subsequent builds; unrelated changes cause refusal.

## Capture after building

Exit any completed benchmark with Ctrl+C. Stop the pool miner before profiling:

```sh
tmux send-keys -t xmrig C-c
python3 capture-jit-profile.py
```

The Python runner refuses to launch while an xmrig/xmrig-miner process is already running. It creates a fresh profile directory, starts a separate offline 1M rx/0 workload under `perf record`, and stops its own process group with SIGINT after 15 seconds (including dataset initialisation). It does not stop or restart the normal pool miner. A later Ctrl+C also cleans up the diagnostic process group. The capture uses the system logical CPU count (32 on the target); `--threads` and `--seconds` may be set explicitly. No pool credentials or live pool traffic are used.

Outputs include capture.log, perf.data, samples.txt, jit-trace.bin, summary.txt and hot-examples.txt. Send summary.txt or its screen first; the full raw capture is not normally needed. Keep hot-examples.txt for follow-up analysis. The captures are in RAM on a diskless system; copy a capture folder to persistent storage if it is needed after reboot. The runner never deletes existing captures.

## How mapping works

A static perf map would be misleading because generated code is overwritten at the same addresses repeatedly. This build writes timestamped code versions and emitted-instruction region boundaries for exactly one selected worker. All workers execute the workload, but only the selected worker's samples are joined to those versions. CLOCK_MONOTONIC is used for the trace and `perf record -k mono`; `perf script --ns -F tid,time,ip` supplies timestamps and sampled addresses.

This is a custom sidecar format and report script, not a perf jitdump integration. Ordinary perf report will still lack these JIT symbols. The Python report joins sampled addresses to the appropriate version by timestamp, groups them by RandomX emission region, and disassembles examples from the matching captured bytes. The epilogue is captured separately. The binary format is explicitly defined by fixed-size structs in jit_trace.hpp and matching Python Struct declarations in report-jit-profile.py.

Snapshot output is capped at approximately 256 MiB. On reaching the cap, a timestamped end marker is written and all later samples are excluded. Only one worker writes the file; other workers never snapshot code. The parser rejects malformed or truncated captures. If an explicit end marker is absent, it conservatively excludes samples at or after the last complete code version. Both the profile build and a nonempty RX_JIT_TRACE path are required to record snapshots; ordinary production builds have tracing disabled.

## Interpretation limits

The summary gives shares of mapped sampled instruction pointers, not operation latency or exact cycle costs. Tracing adds compilation, copying and I/O overhead on the selected worker. Sampling skid, SMT contention and cache effects can bias the profile. CFROUND regions can include NOPs from eliminated rounding updates; consult the actual machine-code examples. The result should identify areas worth investigating, not by itself establish a bottleneck or speedup. Hashrate and wall power from this diagnostic run are not comparable with production measurements. Review outside-JIT samples separately when needed.

## Parser contract tests

```sh
python3 test-jit-profile.py
```

## Validation and remaining checks

The tracing-enabled Linux CPU miner links and passes the offline 250K rx/0 checksum 7D6054757BB08A63 with snapshots enabled. A real 256 MiB trace was parsed and its chronological versions/region bounds checked. Synthetic sampled addresses joined against real captured regions produce the expected classifications. Separate fixture tests cover address reuse, epilogue mapping, thread filtering, capture-end exclusion and truncated input. A capture-runner fixture verifies timed SIGINT and that an unrelated process remains running. The emitter also compiles with tracing disabled. CMake configuration verifies -g, no stripping and RX_JIT_TRACE in the profile build.

Live hardware perf sampling and the complete capture on Alpine remain to be verified on the target. They cannot be claimed as tested from the fixture checks. A failure leaves capture.log and other diagnostic files for inspection. No user hardware measurement data is published by these scripts.
