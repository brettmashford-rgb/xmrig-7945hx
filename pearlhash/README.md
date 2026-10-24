# Independent PearlHash miner development

Version: **0.0.9-commitment-leaf-check**. This remains **not a working miner**.

All 12 offline GPU math checks from v0.0.3/v0.0.4 passed on the user's RTX 5060.
The new independent code constructs fresh matrix commitments, authenticates
Merkle openings and serializes dense PlainProofs; new V2/V3 proofs pass the
pinned official verifier. Both fresh V2/V3 GPU-candidate-to-proof runs also
passed on the user's RTX 5060, with archive/internal checksums verified.
An independent outer transport codec and login-only diagnostic are now available;
the user has confirmed live login, extranonce and notify decoding on the rig.
An independent 76-byte header conversion now matches controlled client-decoder
experiments. The pool's compact matrix reconstruction and target scaling remain
unvalidated. Capture 04 contains a correlated accepted WildRig share, but its
corresponding earlier job notification is absent. The new passive context
collector retains preceding notifications and a later accepted submission for
reconstruction testing; it does not itself assign a job based on timing.
No submitted/accepted custom share or measured speed/power gain exists.

The new independent nonce-tail arithmetic primitive has a native sm_120 kernel
and a small GPU comparison runner. Its kernel body passes 263 CPU comparisons;
All 263 GPU comparisons passed on the user's RTX 5060, with output guards
unchanged and archive/internal checksums verified. The complete captured-share reconstruction
still fails its target, so full pool compatibility remains unresolved.

A separate keyed BLAKE3 chunk-CV kernel now compiles natively for sm_120.
141 synthetic CPU comparisons match the official BLAKE3 portable compressor,
including counters beyond the old 64-MiB cap and 32-bit carry. The CPU kernel
body and guard checks pass. Actual GPU commitment-leaf execution is pending.
These are sparse boundary checks, not a full production matrix commitment.

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
  Merkle/encoding/native hash checks pass. The fresh GPU-to-proof run is pending.
