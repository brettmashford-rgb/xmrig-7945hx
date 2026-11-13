# V85.3: keep the Nsight report in RAM

V85 measured and saved the unprofiled baseline and energy. The RAM-backed V85.2 run downloaded and extracted the CLI successfully, but Nsight could not write its `.ncu-rep` file in the nearly full home directory. This retry stores the temporary download, extracted CLI, Nsight report, and profiler home in `/dev/shm` or `/run`. It saves the small counter JSON only. The V85 baseline is reused.

If Nsight is not already on PATH, the retry uses the same SHA256-pinned NVIDIA Nsight Compute 2025.4.1 Debian package and extracts only the x86-64 CLI files and metric sections into RAM. It requires about 490 MiB free in `/dev/shm` or `/run`; it writes only the compact counter report to the existing V85 results folder. It does not install system packages or alter drivers or global profiler permissions.

The report requires `sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active` and includes integer tensor instruction throughput, SM/DRAM throughput, scheduler, stalls and occupancy. Three exact `a_pair_direct_scan` launches are sampled after eight warmups. The report is an offline diagnostic; replay timing does not replace the V85 speed/energy measurements. No pool or shares are used.
