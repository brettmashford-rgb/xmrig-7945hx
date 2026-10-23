# v0.0.3 GPU math correctness checkpoint

This is an offline test, **not a miner**. Native sm_120 kernels are compiled;
GPU execution is pending on the RTX 5060. No accepted custom shares or measured
speed/power gains exist. The Pearlhash pool encoding is still unresolved.

## Scope

`correctness.cu` independently computes every cumulative int32 matrix product
at rank boundaries, then folds the products into the 16-word transcript. The
CPU harness computes all those products independently with int64 arithmetic
and compares every result. It also compares the GPU transcript against the
expected words. This is a simple scalar GPU baseline, not tensor-core mining.

Inputs contain **pre-noised** matrices. Fixture generation first runs the
existing independent Python reference against the official-generated V2/V3
JSON fixtures, then exports signal-plus-noise matrices and their expected
transcripts. GPU seed/noise generation, digest, commitment construction,
Merkle openings, proof construction, consensus/target handling and the pool
client remain future work. The compact files do not replace the original JSON
fixtures or official proof verifier.

The seven inputs cover V2 and V3, signed extrema, negative products, zeros,
asymmetric tiles, multiple CUDA blocks, 1024 matrix pairs and transcript-slot
reuse. Synthetic extra cases derive expected words with the independent
Python reference; they are not official full-proof fixtures. Host validation
rejects invalid dimensions, unsafe values, truncation, trailing bytes and
incorrect expected transcripts. Checked input bounds prevent int32 overflow.

## Run on the rig

The archive includes the x86_64 executable, native CUDA cubin, source and seven
compact inputs. Requires the installed NVIDIA driver (`libcuda.so.1`), GPU 0
with compute capability 12.0, glibc and libstdc++. No CUDA/Rust toolchain,
libcudart, Python dependency installation, root access or service changes.

From the extracted package:

```sh
sha256sum -c SHA256SUMS
./bin/pearl-gpu-check gpu/correctness-sm120.cubin tests/gpu/*.bin
```

The tiny offline test may run alongside existing miners; it is not a benchmark.
It makes no network connections and changes no clocks or service settings.
Report failures verbatim; CPU success alone does not validate the GPU.

## Rebuild on a development host

Host build: GCC 13.3.0, C++17, `-O2 -Wall -Wextra -Werror`, linked with `-ldl`.
CUDA build: NVIDIA NVRTC 12.9.86 Python wheel, reports NVRTC 12.9;
`--gpu-architecture=sm_120 --std=c++17`. No GPU was used to compile.

```sh
mkdir -p build
g++ -std=c++17 -O2 -Wall -Wextra -Werror gpu/check.cpp -ldl -o build/pearl-gpu-check
python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 build/correctness-sm120.cubin
python3 -m tools.make_gpu_vectors tests/vectors tests/gpu
PEARL_GPU_CHECK="$PWD/build/pearl-gpu-check" python3 -m unittest discover -s tests -v
```

Compiler downloads are development-host-only. NVRTC is not redistributed.
CUDA code and harness use the subdirectory ISC license. Binary dependencies
are system runtime libraries; the CUDA driver is supplied by the rig.

## Validation recorded on development host

- Native sm_120 cubin compilation succeeded (20,816 bytes).
- Host executable compiles with warnings treated as errors.
- Seven input/transcript CPU comparisons pass.
- Parser rejection cases pass; existing seven reference tests still pass.
- CPU comparisons also pass with AddressSanitizer and UndefinedBehaviorSanitizer.
  LeakSanitizer is disabled because the host denies its process inspection.
- No NVIDIA driver/GPU is available here: no kernel launch was tested.
- No performance benchmark, live share submission or pool verdict.
