# v0.0.4 GPU noise and digest correctness checkpoint

This is an offline correctness test, **not a miner**. Native sm_120 kernels
compile. The user confirmed all seven v0.0.3 matrix/transcript tests pass on
an RTX 5060. All five new v0.0.4 GPU noise/digest tests also **passed** on that GPU.
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
is available on the development host. The user subsequently confirmed all five new GPU noise/digest checks pass
on the RTX 5060; archive and internal checksums also passed.
No live pool submissions, accepted shares or performance measurements.


## v0.0.9 keyed chunk commitments

`chunk_commitment.cu` independently hashes complete 1024-byte chunks with a
32-byte key and explicit u64 first-chunk index. Each thread emits a 32-byte
chaining value, with KEYED_HASH / START / END flags and no ROOT flag. Parent
folding must preserve that distinction. A two-chunk root golden checks it.
The host bounds input batches and counter addition before launching; the
kernel ignores out-of-range threads. GPU execution is pending on the RTX 5060.

The supplied 141 synthetic cases include the chunk-index boundary of an 8-GiB
matrix, not a complete 8-GiB computation. No assumption about the pool's signal
matrix layout is established by this component. It supplies a commitment leaf
operation needed for a later independently constructed full GPU proof pipeline.

Build on the development host (no compiler install required on the rig):

```sh
python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 gpu/chunk-commitment-sm120.cubin chunk_commitment.cu
```

The package includes the native CPU hash library, source, CPU kernel-body
checker, synthetic official-compressor CV goldens, fixture and stdlib GPU runner.
`tools/cuda_driver.py` now owns the common driver lifecycle used by the nonce
and commitment checks; each releases only its own context and allocations.


## v0.0.12 exact integer tensor-core prefix check

`mma_correctness.cu` consumes already-noised signed-byte selected matrices. Dense
warp-level `mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32` operations keep exact
int32 prefix accumulators. A separate fold/digest launch preserves the Pearl
transcript rule. All rank-boundary products are compared, as well as words and
digest, with bounded inputs and poison output guards. No FP8 algorithm change.

Register layout authority:
https://docs.nvidia.com/cuda/parallel-thread-execution/#warp-level-matrix-fragment-mma-16832

NVRTC 12.9.86 native sm_120 compilation succeeds; own-code disassembly contains
IMMA.16832.S8.S8. All five GPU cases now pass on the RTX 5060, including
the saved 10x16 / k=32768 / rank=128 input. CPU scalar/parser tests pass;
these are not execution of the hardware MMA instruction. The runner uses four
synthetic cases and optionally a LOCAL PHGPU02 fixture; it saves completion
status locally and never sends fixture contents anywhere. No search loop or
performance claim is made. Existing completed proof/replay checks need not rerun.

```sh
python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 gpu/mma-sm120.cubin mma_correctness.cu
```

## v0.0.13 GPU noise tables to MMA

`noise_mma.cu` includes the same `mma_correctness.cu` implementation and adds
three kernels: `noise_uniform`, `noise_permutation`, and `noise_apply`.
Uniform rows use one keyed hash per 32 bytes; a shared per-side permutation
uses one hash per eight pairs. Selected indices may repeat. Signed signal
bytes plus bounded uniform differences produce exact int8 inputs, without
FP8 conversion. Input seeds remain caller-supplied; no derivation or nonce search.

`tools/check_noise_mma_gpu.py` checks every table byte/pair, every noised byte,
every integer prefix, transcript and digest with poison guards. GPU-produced
noised buffers feed MMA directly; the checker does not upload CPU noised data.
Rows/columns are bounded to 32, k<=65536, ranks32/128/1024 (power-of-two values
through1024 supported). CPU kernel-body checks and independent scalar reference
comparisons pass, including official-generated V2/V3 inputs. New combined GPU
execution now passes all four cases on RTX 5060, including the saved
10x16 / k=32768 / rank=128 input. The standalone MMA path passed earlier.
This correctness harness includes CPU comparisons and device downloads and
makes no throughput or efficiency claim. It is not a production search loop.

```sh
python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 gpu/noise-mma-sm120.cubin noise_mma.cu
```

## v0.0.14 bounded tile scan with compact candidates

`tile_scan.cu` includes the noise/table kernels and the existing MMA implementation.
The fragment operation is now a shared force-inlined helper, used by both the
prefix checker and scanner. A 256-thread CTA evaluates one tile, with up to eight
16x8 MMA subtiles. All warps join unconditional rank-boundary barriers, including
inactive subtiles. Padding is excluded from the XOR fold. Warp shuffle reduction,
block fold, transcript update, keyed digest and target comparison stay on device.

Descriptors map up to 32 selected A/B rows from an existing pool of up to32 per
side. A batch contains at most64 tile queries, sharing seeds and generated inputs.
Bounds are caller-supplied already-scaled u256 values. `scan_target.h` implements
an inclusive little-endian integer comparison, checked on CPU against Python at
word/equality boundaries and randomized values. It is not pool difficulty logic.

The atomic queue stores tile index, u64 generation and digest. Total hit count
and overflow flag are separate; even zero-capacity overflow is explicit. The
host requires complete results and validates candidates with scalar references.
Generation tags detect stale records; this is not yet live-job cancellation.
An optional audit saves transcript words only. No prefix products are written
to global memory by this scan. Normal candidate output is compact.

The CLI checks four synthetic batches and optionally a LOCAL completed PHGPU02
replay input, five maps and eight target/queue scenarios each. All outputs have
guards. Earlier noise-to-MMA hardware checks passed on RTX 5060. The new scan
compiles for sm_120 and now passes all five hardware batches /200 tile-target-queue
checks on RTX 5060, including the saved replay input.
This is a bounded selected-tile search component, not full nonce/job mining or a
pool client. No comparable speed/power measurement has been made.

```sh
python3 tools/compile_correctness.py /path/to/libnvrtc.so.12 gpu/tile-scan-sm120.cubin tile_scan.cu
```

## v0.0.15 range scheduler around the validated backend

No new CUDA code or compilation. The exact v0.0.14 cubin is reused.
`reference/tile_ranges.py` supplies random-access canonical periodic domains,
bounded global-to-local batches, cursor advancement, generation gates and complete
queue retry. `tools/check_range_scan_gpu.py` constructs selected constant signals
and feeds batches to the existing GPU noise/tile scanner. Inputs stay bounded
and are retained over overflow retries, then released at the next batch.

The new rig harness checks all 15 tiles of a small synthetic domain with a
nonce-derived last A-row tail and cancellation/resume, plus two tiles each at
start/middle/end of an 8388608-tile production-shaped domain. Six production tiles
are tested, not the whole domain or an entire nonce. Synthetic seeds/maximum
scaled bounds and full CPU references make this a correctness harness. It has
no pool I/O and does not measure comparable throughput/power. Existing kernel
hardware validation and new scheduler integration now pass on RTX 5060,
including cancellation/resume and all 21 tested tiles.

## v0.0.16 fresh nonce/range/proof integration

No CUDA source/binary change or compilation. The existing noise/tile scanner
now receives CPU-derived seeds bound to fresh synthetic header/config and
nonce-dependent full commitments. `RangeBackend` accepts an explicit already-
scaled bound instead of forcing all-hit tests; its default remains unchanged.
The new `tools/offline_nonce_search.py` stops at a completed target-meeting
batch, independently constructs the selected PlainProof and invokes the rig's
existing official CPU oracle. CPU references still check every tested tile.
This correctness path is not an efficient production worker or benchmark.

CPU commitments, nonce-tail mapping, seed derivation and proof encoding remain
CPU operations. GPU deterministic noise, integer tile scan, transcript/digest,
target comparison and queue operations use the validated v0.0.14 cubin. New
nonce-to-proof GPU/oracle integration is pending. The v0.0.15 scheduler already
passed its rig checks. No live job source, pool client or submitted share.
