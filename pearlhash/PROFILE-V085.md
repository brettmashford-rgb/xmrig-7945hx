# V85: measure the winning pair-direct kernel

V84.1 kept pair-direct: 2.333 M tiles/s over full nonces versus 1.329 M for exact B projection. Projection was 43.04% slower; no amortization break-even was found. V81 layouts, V82 twin B reuse and V83 host dispatch/graphs also failed to replace this winner. V85 changes no scanner instructions and makes no speed promotion.

The bounded offline run verifies the installed packages and unchanged V80 PTX (SHA256 99f53e9f0ae22496b8bf8348b24448060d50cc5d4440ee41a4d2ac04923bf0bf), repeats independent CPU/proof/guard preflight, measures eight unprofiled timing rounds, records a separate host/event diagnostic and three full nonce NVML energy samples after conditioning. Board energy is an approximate sensor estimate, not wall-plug power. NVML GPU activity is not Tensor Core utilization.

Nsight Compute then captures three complete 16K scanner windows near the middle of a production-size synthetic nonce after eight warm-up windows. Only a_pair_direct_scan is selected. Kernel replay timing is excluded from the speed/energy results. Sections cover SM/DRAM throughput, compute pipelines, instructions, scheduler eligibility, warp stalls, memory and occupancy. Cache control and clock control are both none; replay still changes cache state. Stall counters must not be summed as wall-time percentages. Literal measured counters are printed; no automatic bottleneck claim is made.

If ncu is absent, the script downloads the official NVIDIA Debian 13 Nsight Compute 2025.4.1 package (322,492,696 bytes), verifies SHA256 6aacf98f3c55226cf445975d348c297c1c7f785467397c9654cb26307a734d96, extracts it privately using dpkg-deb and deletes the archive. It requires 2 GiB free. No system package installation, driver change, CUDA toolkit installation or persistent profiling permission change is performed. A counter permission error triggers one sudo retry for this diagnostic. If counters remain unavailable, the compact output says so and the suite exits incomplete; it does not substitute estimates.

Reports stay in ~/pearlhash-dev-v0.0.85: baseline.json, hardware-counters.json, counters.csv, pair-direct.ncu-rep, ncu-user.log and (if needed) ncu-elevated.log. No reports are uploaded automatically. The test has no pool connection and submits no shares.

The launcher stops only pearl.service, restores WildRig on exit, and arms an independent 40-minute restart fallback before stopping the service. CPU XMRig is untouched. A 35-minute outer bound and shorter individual profiler bounds apply. Interrupted profiler process groups are terminated before restoration.

Validation before publishing: six host tests cover metric parsing/replication, wrong kernel and incomplete exports, subprocess failure/timeout, actual python -S imports under the split installed package layout, and host/event placement/cleanup. NVIDIA package checksum and CLI section/options checked locally. GPU execution and real counters require the user's rig.

Official references: https://docs.nvidia.com/nsight-compute/NsightComputeCli/index.html and https://developer.nvidia.com/nvidia-development-tools-solutions-err_nvgpuctrperm-permission-issue-performance-counters
