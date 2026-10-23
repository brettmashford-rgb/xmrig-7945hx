# v0.0.4 GPU noise and digest correctness checkpoint

This is an offline correctness test, **not a miner**. Native sm_120 kernels
compile. The user confirmed all seven v0.0.3 matrix/transcript tests pass on
an RTX 5060. The new v0.0.4 GPU noise/digest execution is **pending**.
No custom pool shares or measured speed/power improvements exist.
Pearlhash pool encoding remains unresolved.

## Scope

The independent GPU code now implements deterministic A/B low-rank noise,
signal-plus-noise matrices, every cumulative integer matrix product at rank
boundaries, transcript folding, and the final keyed BLAKE3 digest. Noise seeds
and selected row indices are supplied by offline fixtures. Seed derivation,
commitments, Merkle proofs, proof construction, target/consensus handling and
the pool client remain future work.

`keyed64.h` is an independent fixed-length BLAKE3 compression implementation:
only a 64-byte input, 32-byte key and 32-byte root output are supported. It is
not a general streaming BLAKE3 library. Counter, 64-byte block length and
KEYED_HASH/CHUNK_START/CHUNK_END/ROOT flags are fixed for those inputs. The noise
messages and final transcript hash both satisfy this restriction. CPU and GPU
use the same header; CPU/GPU agreement alone is not independent validation.
The independent Python reference and Python blake3 library supply expected
noise, transcript and digest values. Official-generated V2/V3 fixture outputs
are also checked before exporting compact test inputs.

The host compares every generated noised element and cumulative product,
all 16 transcript words, and all 32 digest bytes. GPU noise outputs are poisoned
before launch; their generated matrices feed the product kernels directly.
The host computes cumulative products separately with int64 arithmetic.
Input bounds prevent int32 overflow and 32-bit noise-index wraparound.

This remains an intentionally simple scalar GPU correctness baseline: three
small BLAKE3 calls per noise element, no tensor-core optimization or performance
claims. The tiny test may run alongside the existing miners; it is not a
benchmark. No clock, driver or service changes; no network code in the binary.

## Test inputs

- Seven preserved PHGPU01 tests cover V2/V3 products/transcripts, signed extrema,
  zeros, asymmetric tiles, multiple blocks and transcript-slot reuse.
- Five PHGPU02 tests add noise/digest: official-generated V2 and V3 plus synthetic
  rank 32, rank 1024 and repeated/non-monotonic row indices. Rank-1024 includes
  the largest row index supported without 32-bit uniform-index wraparound.
- Original official-generated JSON proofs remain in the repository, rather
  than being duplicated in this small incremental archive. Synthetic additional
  cases are Python reference cases, not official full-proof fixtures.
- Four host test methods cover all 12 inputs and 13 malformed-input cases,
  including invalid seeds, indices, signals, expected digests and truncation.

PHGPU02 layout: PHGPU02 NUL; LE u32 rows/cols/k/rank; expected pre-noised A/BT
as LE i32; 16 expected transcript words; 32-byte A/B seeds; A/B row indices;
signal A/BT as LE i32; 32-byte expected digest. PHGPU01 retains its old layout.

## Run on the rig

From the extracted package:

```sh
sha256sum -c SHA256SUMS
./bin/pearl-gpu-check gpu/correctness-sm120.cubin tests/gpu-noise/*.bin
```

Requires GPU 0 compute capability 12.0, the installed NVIDIA driver
(`libcuda.so.1`), glibc 2.34+ and libstdc++ with GLIBCXX_3.4.32. No CUDA/Rust
compiler, libcudart, Python packages or root privileges are needed.
The archive contains source, compiled cubin, executable and compact inputs.

## Rebuild on a development host

Host: GCC 13.3.0, C++17, -O2 -Wall -Wextra -Werror, linked with -ldl.
GPU: NVRTC 12.9.86 wheel (reports 12.9), sm_120, C++17; no GPU used to compile.
Compiler dependencies are development-host-only and are not redistributed.
From the repository's pearlhash directory with reference dependencies installed:

```sh
mkdir -p build
g++ -std=c++17 -O2 -Wall -Wextra -Werror gpu/check.cpp -ldl -o build/pearl-gpu-check
python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 build/correctness-sm120.cubin
python3 -m tools.make_gpu_vectors tests/vectors tests/gpu
python3 -m tools.make_noise_vectors tests/vectors tests/gpu-noise
PEARL_GPU_CHECK="$PWD/build/pearl-gpu-check" python3 -m unittest discover -s tests -v
```

## Validation status

v0.0.3: compiled here, then seven GPU tests passed on the user's RTX 5060.

v0.0.4: native sm_120 compilation succeeded; 12 CPU inputs and malformed-input
rejections pass. AddressSanitizer and UndefinedBehaviorSanitizer host checks
pass with LeakSanitizer disabled because host process inspection is restricted.
The existing seven Python reference tests also pass. No NVIDIA GPU or driver
is available on the development host. New GPU noise/digest execution is pending.
No live pool submissions, accepted shares or performance measurements.
