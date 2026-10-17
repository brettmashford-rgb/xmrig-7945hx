# Full-workload screening before target builds

The FDIV ternary-mask and paired-load experiments did not establish a worthwhile target improvement. Component timings alone were not enough to select a useful mining optimisation. New candidates should be checked against complete RandomX hashes locally before asking for another Alpine build.

`tools/screen-host.py` runs baseline, candidate, candidate, baseline (ABBA), exits each miner automatically when the benchmark finishes, writes raw logs/results and aborts on checksum disagreement with the pinned upstream RX_0 reference (default seed). It refuses to overwrite existing output. It passes no pool, wallet or submission arguments. A screen is not proof of speed or power improvement on a different machine.

Example for developers with two prebuilt, otherwise-matching binaries:

```sh
python3 tools/screen-host.py /path/to/baseline /path/to/candidate --threads=8 --size=250K --output=/path/to/new-results
```

Use the same pinned XMRig revision, compiler and build options for both binaries. The runner disables huge pages for the local comparison and does not change persistent miner configuration or startup. It does not measure wall power. Small differences can be obscured by shared-host scheduling, memory topology, clock changes and profiling overhead. Benchmark hashes match only when size, algorithm and seed match.

The runner was checked for successful ABBA completion, checksum-mismatch abort and existing-output refusal, and exercised against actual miner binaries.

## Initial local build environment

- XMRig v6.26.0, upstream SHA b2ca72480c58d197e18c885d9fc1a0c8d517e60a, plus the existing AES prefetch patch at 7168.
- GCC 13.3, C++11/Release, IPO/LTO off; CMake 4.4.4 with policy minimum 3.5 for legacy dependencies.
- libuv 1.52.1, commit 1cfa32ff59c076ffb6ed735bbc8c18361558661f, built locally.
- AMD EPYC Zen 4 virtual host; 8 worker threads. Hardware topology and OS differ from the target Ryzen 7945HX on Alpine GCC 15.2.
- HWLOC, TLS, HTTP, MSR, CUDA, OpenCL, GhostRider and KawPow disabled in both local binaries; RandomX, assembly and benchmark enabled. Developer profiling enabled in both local binaries. These are local development build options, not proposed target miner tuning.
- Initial full baseline run: 250K hashes, 63.966 seconds, 3908.3 H/s, checksum 7D6054757BB08A63. Do not compare this exploratory run directly with a later isolated candidate to infer a small gain.

## Reciprocal-multiply candidate

`jit-rcp.patch` rewrites the constant multiply emitter to use `movabs rax, reciprocal; imul destination,rax` rather than using stack-memory multiply operands for the first 16 constants in each program. This removes those repeated stack reads but increases emitted code bytes and instruction count. It leaves constant-multiply arithmetic and branch register-use bookkeeping intact. It is an experimental candidate, not a selected optimisation.

Dependent-chain and independent-chain component comparisons showed no clear, consistent advantage. Full-workload ABBA results are recorded in `results/2026-10-17-host-rcp.json`: baseline 3813.9 / 3853.3 H/s; candidate 3870.7 / 3914.8 H/s. Means: 3833.6 versus 3892.75 H/s (+1.543%). All checksums match the pinned upstream 250K reference. This is encouraging enough for a short target test, but two runs per build are insufficient to establish a reliable gain on a shared host. The separate initial baseline run was 3908.3 H/s, demonstrating material variability. A matching checksum checks the tested workload, not all possible RandomX inputs.

To reproduce the initial local build after providing CMake, libuv headers and its static library:

```sh
cmake -S /path/to/patched-source -B /path/to/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DUV_INCLUDE_DIR=/path/to/libuv/include -DUV_LIBRARY=/path/to/libuv.a -DWITH_HWLOC=OFF -DWITH_TLS=OFF -DWITH_HTTP=OFF -DWITH_MSR=OFF -DWITH_CUDA=OFF -DWITH_OPENCL=OFF -DWITH_GHOSTRIDER=OFF -DWITH_KAWPOW=OFF -DWITH_PROFILING=ON
cmake --build /path/to/build -j 4
```

The no-TLS executable is named `xmrig-notls`. Keep separate baseline/candidate executables and change only the candidate source. The tested baseline source has now been restored after creating the candidate binary.
