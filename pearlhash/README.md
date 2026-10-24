# Independent PearlHash miner development

Version: **0.0.15-periodic-range-scheduler**. This remains **not a working miner**.

The user's RTX 5060 has passed the offline GPU math checks, 263 nonce-tail
comparisons, 141 keyed commitment-leaf comparisons and the empty launch. Fresh
V2/V3 proofs built with GPU commitment leaves, CPU parent folds and GPU math
also pass the pinned official CPU verifier on the rig. Checksums verified.
Seed derivation, parent folding and Merkle opening construction remain CPU work.

Independent pool transport/login and header decoding are implemented. The
saved existing-miner share now has a CPU mathematical reconstruction:
for this observed profile, `sb: 1` enables fill byte 64. A matching saved notification with
explicit V3 derivation yields the recorded nonces' target-meeting digest. New
streaming CPU code builds both complete matrix roots and sparse openings,
including the logical 8-GiB B matrix, without allocating a full matrix/tree.
Its roots match a separate streaming BLAKE3 reference, and its selected math
matches the separate C++ checker at 10x16 / k=32768 / rank=128.

The saved existing-miner replay has now passed GPU math and official CPU
proof verification on the rig. General job/version/target compatibility and production search are
not established by one recorded share. No custom share has been submitted or
accepted, and no speed or power improvement has been measured.

A new independent integer tensor-core matrix kernel compiles natively for
sm_120; disassembly confirms IMMA.16832.S8.S8. It compares every cumulative
rank-boundary product, transcript word and digest with a scalar CPU calculation.
All four synthetic cases and the saved 10x16 / k=32768 / rank=128 input now pass
on the RTX 5060: every prefix product, transcript, digest and output guard matches.
It consumes already-noised selected inputs and is not yet a mining search loop.
No performance improvement is claimed before measurement.

The next compiled component generates reusable uniform/permutation noise tables
and signed noised bytes on the GPU, then feeds the same device buffers directly
into the tensor-core path. Seeds, selected indices and signal bytes remain
supplied inputs. Independent CPU noise/math and actual noise-kernel-body CPU
checks pass. All four combined-path cases now pass on the RTX 5060, including
the saved 10x16 / k=32768 / rank=128 input. No production search
loop or pool submission has been added.

A compiled bounded tile scanner now reuses GPU-generated inputs across selected
tiles, folds transcripts and hashes on the GPU, and compares caller-supplied
scaled u256 bounds. It returns generation-tagged candidate records with explicit
overflow detection instead of copying every prefix product to the CPU. CPU
target/queue/schema checks pass. All five scan batches now pass on RTX 5060,
covering 200 tile/target/queue checks, including the saved replay input. This
is not yet a full nonce/job search or a custom pool-submitting miner.

See [independent proof pipeline](proof/README.md),
[GPU math scope](gpu/README.md), [login-only pool probe](docs/pool-probe.md),
[existing-miner submission capture](docs/share-capture.md), and [downloads](RELEASES.md).

## Source and implemented components

Authoritative upstream: https://github.com/pearl-research-labs/pearl

Pinned commit: `82e6eee7076aafe10123e08db78f100d270c0582`.

- `oracle/`: offline Rust CLI adapter to the pinned official `verify_plain_proof`
  implementation. Generates synthetic V2/V3 fixtures and checks serialized
  PlainProof inputs. It intentionally reuses the official verifier as an oracle;
  this is not an independent full verifier implementation.
- `reference/seeds.py`: independent dense legacy/V3 seed derivation, compared
  with upstream published seed goldens.
- `reference/dense.py`: independent scalar noise generation, cumulative matrix
  products, jackpot transcript and final digest. Compared element-by-element
  with fixtures generated and verified by official Rust code. It does **not**
  authenticate Merkle openings or implement all consensus/target checks.
- `tests/vectors/official-v2.json` and `official-v3.json`: synthetic offline
  cases with serialized proofs and intermediate expected values. V3 uses
  k=4096/rank=128, exercising transcript-slot reuse. These are generated with
  upstream code, not pre-existing official published full-proof goldens.

Protocol findings: [docs/reconnaissance.md](docs/reconnaissance.md).
Benchmark/release gates: [docs/validation.md](docs/validation.md).

## Run the v0.0.2 CPU binary

The v0.0.2 Linux x86_64 archive includes `bin/pearl-cpu-oracle` (glibc 2.34+ and
libgcc_s required). No CUDA or Rust compiler is needed to run it. Runtime makes
no network connections. From the extracted directory:

```sh
RAYON_NUM_THREADS=2 ./bin/pearl-cpu-oracle verify tests/vectors/official-v2.json
RAYON_NUM_THREADS=2 ./bin/pearl-cpu-oracle verify tests/vectors/official-v3.json
```

Expected: `VALID: official offline CPU verifier; not a pool verdict` twice.
No service or clock settings are changed. Tested on the development host;
both V2/V3 fixtures also passed on the user's Debian rig. `SHA256SUMS` in the archive
covers source files, the Git bundle and binary.

## Run independent CPU checks

Python 3.10+; dependency installation contacts PyPI. Runtime/tests do not.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

## Build and restore Git history

See [oracle/README.md](oracle/README.md). Cargo.lock and the exact upstream Git
revision are committed. Rust 1.99.1 was used. The separate [GPU test build](gpu/README.md) uses NVRTC 12.9.
Building fetches dependency sources/submodules and takes more space than the
executable alone. Do not install that toolchain into the small rig persistence.

The v0.0.2 release archive includes a self-contained Git bundle. From its directory:

```sh
git clone pearlhash-dev.bundle ../pearlhash-dev-git
```

The bundle preserves the initial standalone commits and tags. Current development is hosted in the `pearlhash/` subdirectory of https://github.com/brettmashford-rgb/xmrig-7945hx.
Compiled binaries belong to release archives rather than Git history.

## Project commitments

- Independent miner source; no WildRig wrapper or binary patches.
- No developer-fee mining, telemetry, automatic updates or hidden endpoints.
- Future mining connections must be explicitly configured.
- Preserve working WildRig, XMRig and autostart during separate development.
- Report compilation, CPU correctness, GPU correctness and pool acceptance separately.
- Never call the custom miner working until real shares are accepted.

## Validation performed

- Seven Python tests pass: published seed goldens, official-generated V2/V3
  intermediates, bad inputs, changed signal and wrong seed context.
- One Rust integration-style test passes for both versions: proof serialization
  round trip, official acceptance, changed header/matrix rejection and rejection
  under an intentionally tiny share target.
- CLI verifies both saved fixtures. Corrupted proofs are rejected in tests.
- The complete upstream ZK/circuit test suite was **not** executed.
- v0.0.3: seven GPU matrix/transcript checks passed on the user's RTX 5060.
- v0.0.4: native sm_120 noise/digest kernels compile. Twelve CPU math cases and
  13 malformed-input cases pass, including sanitized host checks with leak
  detection disabled due to process-inspection restrictions.
- v0.0.4: all five new GPU noise/product/transcript/digest checks pass on the
  user's RTX 5060. Across v0.0.3/v0.0.4, all 12 offline GPU tests have passed.
- No custom pool share or benchmark. The offline transport analyzer reproduces
  capture framing; the pool codec and field semantics remain unresolved.

- v0.0.5: fresh independent V2/V3 PlainProof construction passes the official
  verifier on the development host; ten official negative cases reject, and
  Merkle/encoding/native hash checks pass. The fresh GPU-to-proof run also passed on the rig.

## Periodic range scheduling checkpoint

Random-access domain planning now maps global tile IDs into bounded GPU batches
without enumerating all matrix indices. The observed 10x16 production-shaped
domain contains 8388608 tiles. A resumable in-memory cursor, generation gates
and complete-result overflow retry are implemented around the validated backend.
57 CPU tests pass / two prior oracle/vector cases skip. GPU integration of the
new scheduler is pending; the unchanged cubin is the rig-validated v0.0.14 binary.
The harness checks 15 small-domain tiles plus six production-domain tiles at
start/middle/end; it does not scan an entire nonce or submit anything to a pool.
Seed derivation/commitments and live job integration remain separate work.
