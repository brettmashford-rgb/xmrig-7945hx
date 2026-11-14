# V0.0.86 OpenCL tensor-core feasibility probe

This is the first step in evaluating an OpenCL implementation. It checks that
the NVIDIA OpenCL compiler on the target host accepts inline PTX for the same
signed int8 to int32 `mma.sync.m16n8k32` operation used by the CUDA scanner.
The K=128 output is compared against a CPU reference before any timed run.

The timed workload repeats exact matrix products using OpenCL C plus NVIDIA
inline PTX. It is a tensor-core path feasibility and throughput measurement;
it is not a PearlHash nonce scanner and its result is not a mining hashrate.
There is no pool connection, share submission, miner configuration change, or
WildRig binary replacement. The launcher temporarily stops `pearl.service`
for a cleaner GPU measurement and restores it on exit, with a systemd timer as
a fallback. The separate CPU XMRig service remains running.

The host uses Python `ctypes` and the driver's OpenCL ICD, so no CUDA toolkit,
OpenCL headers, pip package, or system package installation is needed. A
successful run only establishes the OpenCL/inline-PTX compute route; the
validated nonce/proof and candidate-handling pipeline still needs an OpenCL
port and independent proof checks before it can replace production scanning.

Expected command output ends with `OPENCL TENSOR PROBE:` JSON. Send that line
plus any preceding error text. The key fields are correctness, device/driver,
K, warps, median wall time, estimated integer operations per second, and the
result checksum.
