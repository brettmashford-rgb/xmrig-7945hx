# Independent PearlHash miner development

Version: **0.0.3-gpu-math-check**. This remains **not a miner**. Native sm_120
CUDA kernels and an offline Linux test harness now compile. GPU execution on
the RTX 5060 is pending. No pool client, accepted custom-miner share or measured
speed/power improvement exists. Pool encoding remains unresolved.

See [GPU correctness checkpoint](gpu/README.md) and [downloads](RELEASES.md).
The kernels check pre-noised cumulative products and transcript folding only.

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

## Run the included CPU binary

The Linux x86_64 archive includes `bin/pearl-cpu-oracle` (glibc 2.34+ and
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

The release archive includes a self-contained Git bundle. From its directory:

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
- Native sm_120 compilation succeeds; seven compact CPU input/transcript checks
  and malformed-input rejection pass. Sanitized host checks pass with leak
  detection disabled due to host process-inspection restrictions.
- No GPU execution, custom pool share or benchmark yet.
