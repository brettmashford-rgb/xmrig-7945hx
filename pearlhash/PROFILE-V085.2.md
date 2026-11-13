# V85.2: capture direct tensor-pipe counters using RAM

V85 measured the unprofiled baseline and energy successfully. The first counter run failed because persistent free space was below 600 MiB. V85.2 reuses that baseline and stores no profiler package or runtime in the miner's home directory.

If `ncu` is not already on PATH, the retry downloads the pinned NVIDIA Nsight Compute 2025.4.1 Debian package (322,492,696 bytes; SHA256 `6aacf98f3c55226cf445975d348c297c1c7f785467397c9654cb26307a734d96`) and keeps both the download and the approximately 100 MiB command-line extraction in `/dev/shm` or `/run`. It needs about 470 MiB free in one of those RAM-backed locations and 40 MiB for the saved report. The temporary files are removed when profiling exits. It does not install packages or change drivers, toolkit or global profiler permissions.

The capture requires the hardware counter `sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active` and reports integer tensor instruction throughput separately from overall SM and DRAM throughput. It profiles three exact `a_pair_direct_scan` launches after eight warm-ups on a synthetic, offline job. These Nsight kernel-replay timings are excluded from the saved V85 speed and energy measurements. A permission issue gets one temporary sudo retry. Missing counters remain a clear failure; there are no substitute estimates.

The saved V85 baseline remains intact. Retry output is saved at `~/pearlhash-dev-v0.0.85/hardware-counters-retry.json` and `~/pearlhash-dev-v0.0.85.2/counter-retry-result.json`. No pool connection or shares are involved. The launcher stops only WildRig's `pearl.service` and restores it with an independent 40-minute fallback.
