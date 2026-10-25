# Independent PearlHash miner development

Version: **0.0.17-virtual-fragment-cache**. This remains **not a working miner**.

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
new scheduler now passes all rig checks, including cancellation/resume and all
21 tested tiles. The cubin remains the validated v0.0.14 binary.
The harness checks 15 small-domain tiles plus six production-domain tiles at
start/middle/end; it does not scan an entire nonce or submit anything to a pool.
Seed derivation/commitments and live job integration remain separate work.

## Fresh nonce-to-proof integration

A new synthetic offline pipeline binds header/config and nonce-dependent full
matrix commitments to explicit V2/V3 seeds, searches for an actual non-maximal
target-meeting range candidate, builds its independent PlainProof and invokes
the existing official CPU oracle. Commitments/seed derivation/proof work remain
on CPU; noise and candidate scanning use the unchanged validated CUDA binary.
60 development CPU tests pass / two prior oracle/vector cases skip. New roots
and proof openings match separate materialized CPU trees; stale nonce/job/target
bindings reject. CPU preparation finds V2/V3 candidates and builds proofs.
Combined GPU and official CPU verification now pass on the rig for both fresh
V2/V3 proofs. The development host has no Rust compiler or oracle executable.
No live pool connection, submitted share, production nonce completion or speed/
power improvement is claimed. This remains development, not a working miner.

## Virtual fragment/noise cache checkpoint

A new sm_120 virtual-input module caches full global uniform/permutation noise tables
and forms constant-signal/noise signed bytes as MMA fragments load. The virtual
scan does not allocate/upload signal or noised matrices. The final A-row nonce
tail is preserved. Its table payload is capped at 64 MiB; the production-shaped
synthetic profile uses 34472080 payload bytes, plus small keys/guards/dispatch data.
The original materialized wrapper and virtual wrapper share one MMA/fold/queue
body. 63 CPU tests pass / two prior oracle/vector cases skip. Native uniform/
loader code matches CPU references, including counter limits and signed bytes.
The RTX 5060 run passes the new virtual GPU checks, the wrapper regression and
a fresh virtual-path V3 proof accepted by the official offline CPU verifier. This is a correctness harness, not a measured speed/power
result or a complete production nonce worker. No custom-miner pool submission has occurred.

The v0.0.17 distribution is plain source plus readable compiler-generated PTX,
loaded/JIT-compiled by the existing NVIDIA driver. The existing verified v0.0.16
CPU library is reused. No compressed archive or new native binary is distributed
for this version. The source-file manifest in releases/ binds paths/sizes/hashes.
No toolkit installation is required. Driver-JIT execution now passes on the rig.



## Global range batches (v0.0.18)

The virtual backend now accepts lazy batches of up to 64 global tile maps without
sharing the materialized backend's 32-row/column pools. One nonce noise cache is
retained across dispatches and overflow retries. Global tile IDs and the existing
generation/cursor delivery gates are preserved. Every tested tile still has an
independent CPU reference; this is not yet a fast production worker.
Five new CPU tests and CPU-only integration pass. The new integration checks
130 small-domain tiles in batches of 64/64/2 and two production-shaped tiles
across an A-pattern row boundary. The subsequent RTX 5060 run passes both new
GPU integration checks, including overflow and stale-result discard/resume. Reuses the already-validated v0.0.17 PTX and existing CPU library; no
new compilation, proof regeneration or capture. No pool submission or gain claim.


## Candidate-only CPU validation (v0.0.19)

A new host search path feeds the unchanged validated virtual GPU kernel without
precomputing CPU transcripts for every tile. Complete returned candidates are
independently recomputed on CPU; empty queues require no candidate math, and
partial queues must retry before validation/delivery. Queue lengths, counts,
overflow, global-query slots, generation tags, bounds and buffer guards are
checked. Misses are not independently recomputed in this search path; a separate
full-reference harness compares entire hit sets for bounded synthetic cases.

Four new CPU tests and CPU-only search/proof preparation pass. The subsequent
RTX 5060 run passes all candidate-path GPU checks and a fresh V3 proof accepted
by the official offline CPU verifier: 64 tiles scanned, 13 returned candidates
CPU-checked. This count is not a speed or efficiency measurement.
No new GPU compilation or toolkit is needed. No full production nonce completion,
live pool submission, accepted custom share or measured speed/power gain is claimed.


## Pool job state (v0.0.20)

An explicit dense V3/rank128 profile now serializes the 52-byte mining config,
combines it with the decoded 76-byte pool header to derive the job key, and
scales the supplied little-endian share target. Zero/overflowing share bounds
reject. Login acceptance, assigned extranonce and a supported notify must all
be present before a job snapshot is available. Job/target/extranonce replacement
and connection reset invalidate prior generations. No socket or submit path is
included yet. The assigned extranonce is retained without claiming that its
mapping to a future compact-submit worker_nonce has been verified.

Five new CPU tests and isolated synthetic-message integration pass. The rig
check compares job key/target with the completed local replay facts, then replays
the existing independent login exchange through the new state machine. No matrix
commitment, GPU math or proof test is repeated. The rig saved-input integration now passes: job key/bound match, independent
login state is ready, and replacement/reset invalidate stale jobs. The 124 retained payload bytes and token remain opaque; an explicit
profile is not inferred from those bytes. No live mining or custom pool verdict.


## Live job receiver (v0.0.21)

The new receiver connects once to an explicitly configured endpoint, sends one
independent login and feeds strict bounded transport frames into PoolSession.
It handles fragmented/coalesced reads and invalidates active work on every
connection end. It has no submit method or automatic reconnect. Callbacks must
be quick; an eventual GPU worker needs its own execution thread/queue.

Five receiver CPU tests and the prior five session tests pass using controlled
socket objects, with no development-host connection. The source-package tests
and redacted-report CLI smoke also pass. Actual live pool reception now passes
on the rig: fresh login/extranonce/notify produced a current job with a 224-bit
scaled target; disconnect invalidated it. The runner uses the locally saved wallet, a separate diagnostic
worker name and the explicit verified V3/rank128 profile; it stops at the first
ready job or after the bounded receive window. No GPU, proof or share submission.


## Job-driven search engine (v0.0.22)

The new engine takes a PoolJob snapshot, its explicit matrix profile and its
share bound through nonce commitments, GPU candidate search and independent
proof construction. Matrix dimensions and target come from the job instead of
the earlier synthetic test constants. Work checks the session generation before
and after expensive stages and range dispatch. An in-flight native commitment
call is not interruptible; its result is discarded if the job changed.

Worker and miner nonces are explicit caller inputs. No mapping from assigned
extranonce is inferred. This is an engine component, without a socket worker
thread, submission method or automatic service replacement. Four new CPU gate/
binding tests pass, and a complete CPU-emulated synthetic proof path passes
locally. The new 160x192 V3 session-to-GPU-to-official-verifier integration now
passes on the RTX 5060. It reuses the validated PTX module and CPU library.


## Receiver/search worker (v0.0.23)

LatestJobWorker supplies a single search thread and a one-slot latest-job
mailbox. Receiver callbacks only enqueue work; socket reads continue during
native commitment preparation and GPU dispatch. Pending replacements collapse
to the latest job; stale in-flight results are discarded. The processing thread
owns its CUDA context and joins at shutdown. Native commitment calls still
cannot abort mid-call, so a connection deadline may be followed by a wait for
the current native stage to return.

The new live runner makes one connection, receives for up to 180 seconds by
default, and attempts one fresh production nonce with a bounded 16-tile window.
It uses the exact received target, not an easier test target. Preparation is
CPU-streamed (8 GiB logical B matrix); uniform tables/tile search use the existing
GPU module. It records component wall times under concurrent existing mining,
not miner throughput. No full nonce completion or performance claim.

Assigned extranonce is provisionally supplied as worker nonce only for this
no-submit experiment; its required compact-submit mapping remains unproven.
No proof construction, submitted share, miner replacement or clock changes.
Five deterministic concurrency tests, the five receiver tests and a mocked CLI
lifecycle/redaction smoke pass locally. Actual live GPU integration now passes on the rig: production commitments/
seeds, 16 tiles at the received target, and joined shutdown. Observed wall times
were 29.404s B preparation, 0.583s nonce preparation and 0.074s bounded scan;
these are component times under concurrent existing mining, not throughput.


## Persistent nonce search (v0.0.24)

NonceSearch owns one candidate backend/cache across multiple pausable search
windows. Its cursor records committed global tile IDs, so the next window
continues without repeating tiles or regenerating the nonce noise tables.
Overflow retries keep the same cache. Job replacement, setup/dispatch failures
and explicit close release owned resources; the caller retains its CUDA context.
The existing search_nonce entry point now uses this implementation.

Six new CPU lifecycle/cursor tests and four prior job-engine tests pass. The
isolated source package and mocked eight-window CLI/report checks pass. The
new live runner defaults to 4,096 tiles in eight 512-tile windows, using the
actual target and one nonce cache. It records cache setup and separate window
wall times. The unchanged PTX and CPU library are reused. GPU execution of this
new multi-window path now passes: 4096 tiles, 64 batches, eight windows and one
cache in 1.086s including 0.049573s cache setup. B preparation took 29.425s and
nonce preparation 0.573s under concurrent existing mining; no full nonce, proof/submission or speed
claim. The assigned-extranonce/submit-worker mapping remains provisional.


## Larger GPU dispatch (v0.0.25)

The existing virtual_tile_scan ABI/kernel uses a variable query_count. A new
bounded host path packs up to 4,096 descriptors/targets per launch, with an
equally bounded tagged candidate queue. The GPU module and tile math are
unchanged. WideRangePlan preserves global tile IDs; NonceSearch accepts a plan
factory to combine larger batches with its existing persistent cache/gates.
CPU recomputation remains limited to complete returned hits; identical queries
in a dispatch share one CPU reference. Partial queues still require retry.

Five new CPU tests and six prior persistent-search tests pass, including maximum
queue slots, malformed limits/tags/counts, exact descriptor compatibility,
production row boundaries and wide overflow/global-ID integration. Mocked
correctness and same-nonce comparison CLI/report checks pass locally.

The rig block first checks five larger-grid/queue scenarios (4,096-query all-hit,
all-miss, mixed overflow/complete, and a 67-query partial grid) against independent
CPU references for four small repeated queries. It then compares 64-query and
4,096-query dispatch on the same fresh production nonce/target. Each path builds
one cache; reported window timings exclude cache setup. This is component
measurement under existing mining, not miner throughput or a proven speedup.
Actual GPU checks and the same-nonce comparison now pass. Five queue/grid
cases pass; cache-excluded 4096-tile times were 1.043411s (64 queries/launch)
and 0.389395s (4096 queries/launch), under concurrent existing mining. No proof construction, submitted share or service/
clock change. Live nonce mapping and custom accepted shares remain unvalidated.


## Per-warp tile kernel (v0.0.26)

A new independent kernel assigns one complete query to each warp, up to eight
queries per block. Each warp computes the query's MMA subtiles, reduces the
prefix fold within its lanes and keeps transcript slot i in lane i. It removes
the old cross-warp shared transcript/barriers. Queue ABI, target test, nonce
inputs, generation tags and candidate CPU checks are preserved.

Readable sm_120 PTX was compiled with NVRTC 12.9.86 and reproduced byte-for-byte
using the included build helper. The new entry has no block barriers in the
generated PTX. Source, inherited headers, compiler metadata and actual PTX are
included; no opaque archive or compiler installation on the rig is needed.

Two host launch/ABI tests and five preceding wide-dispatch tests pass. Mocked
20-case correctness/report and same-nonce kernel-comparison smokes pass locally;
these do not execute a GPU. The rig check independently compares transcripts,
digests, equality/overflow queues, guards and generation tags for one/two/four/
eight-subtile layouts, ranks32/128/1024, padding/signed inputs and nonce tails.
Only after those pass does it compare the new and old kernels at 4096 production
tiles on the same fresh nonce/target. The corrected rig diagnostic now passes all20 cases; same-nonce cache-excluded
4096-tile times were 0.407870s (block) and 0.234011s (warp).
No proof construction, submitted share, service/clock change or miner throughput
claim. Assigned-extranonce/compact-submit mapping remains provisional.


## v0.0.26 transcript checker correction

The first rig diagnostic stopped before a live connection because the checker
compared tuple(CPU transcript bytes), length64, against sixteen decoded GPU u32
words. The reference returns packed little-endian bytes. The fix decodes them
with struct.unpack('<16I', raw) before comparing every word. No kernel/PTX,
digest/target check, guard or queue validation changes. The corrected real GPU run now passes all20 correctness cases and the
same-nonce comparison.

Two regression tests cover full-width u32 values, invalid reference formats and
real scalar-reference byte output. The corrected twenty-case CLI mock uses the
actual decoded GPU audit format; the previous mock incorrectly supplied byte
tuples and missed the representation mismatch. Isolated patch tests pass.
The small fix manifest downloads the checker/test source only and reuses the
verified v026 package/PTX; the failed report and original files are preserved.


## Production-profile shared cache (v0.0.27)

The new specialised kernel accepts exactly 10x16 tiles, K32768, rank128 and
constant fill64. It keeps each query's 26x128 signed uniform coefficients in a
transposed warp-owned shared cache (26KiB/block), and reuses the same four A
fragments across both MMA operations. It preserves exact integer accumulation,
nonce-tail handling, lane-held transcript, keyed digest, target and queue tags.
Unsupported profile/shapes reject before launch; the validated general warp
path remains available as the comparison baseline.

Actual readable PTX was compiled with NVRTC12.9.86 and reproduced byte-for-byte.
The updated build helper also reproduces the unchanged v026 PTX by default.
Three new CPU selector/guard tests and two prior warp host tests pass. Mocked
15-case correctness and same-nonce comparison CLI/report checks pass. Isolated
package tests pass. These local checks do not run an actual GPU.

The rig diagnostic checks first/last production-domain indices, nonce tails,
reversed maps, extreme tail values, full/partial grids, exact transcript/digest
matching, target equality and queue overflow against independent CPU references.
It then compares the validated general warp and specialised shared-cache
kernels on the same production nonce/target. The real GPU run now passes all15 cases and the same-nonce comparison: warp
0.246530s, specialised kernel0.141634s, cache excluded. No share submission, proof test, service/clock change or overall
miner speed claim.


## Compact-share component and status-schema inspection (v0.0.28)

The new prepare_share component calls the existing independent proof builder
to recheck candidate math, nonce binding, roots/seeds and Merkle openings before
forming the observed compact-submit fields. Prepared parameters use explicit
job dimensions/patterns and caller-supplied nonces; assigned-extranonce mapping
is not inferred. No recorded existing-miner share is replayed.

SubmissionGate is a one-connection component with a finite-timeout socket
attachment, current-job check/write under the session lock, monotonic request
IDs, pending limits and bounded recent/history ledgers. Only matching integer
request IDs with a well-formed explicit positive response count as accepted.
Unknown/duplicate replies cannot add credit; write failures invalidate the
connection without automatic retry. An eventual receiver adapter must attach/
detach the owned socket and feed responses; this is not yet wired into the live
runner and has not sent a real custom share.

Eight local CPU/socket tests pass, including actual independently constructed
synthetic proof preparation, compact payload fields, stale gates, correlation,
reject/error/disconnect cases and concurrent replacement versus a locked write.
These use simulated sockets, not a pool. Two saved-status inspector tests and a
real CLI smoke against synthetic JSON pass. The rig block only reads existing
decoded report_info messages to establish status-report parameter structure;
strings/credentials are redacted while numeric values/types are retained.
No new capture, GPU test, pool connection or share submission in that inspection.
