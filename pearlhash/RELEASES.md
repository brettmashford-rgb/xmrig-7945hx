# PearlHash development checkpoints

## v0.0.26-per-warp-kernel

New one-query-per-warp integer MMA/fold kernel. Transcript slots stay in lanes,
removing cross-warp shared-memory prefix barriers. Actual readable PTX built
with NVRTC 12.9.86; byte-identical rebuild passed. Full source/headers and build
metadata are included. No new compiler/toolkit required on the rig.

Two CPU host-contract tests and five prior wide-dispatch tests pass. Mocked
correctness/report and same-nonce comparison CLIs pass. The rig will check 20
independent transcript/digest/queue cases over four layouts before a live old-
versus-new kernel comparison on the same production nonce. GPU result/speedup
is pending. No share submission or service/clock change.


## v0.0.25-wide-dispatch

Fourteen UTF-8 source files; unchanged PTX/CPU library. New host packing/queue
path supports up to 4096 queries, preserving the same kernel ABI, target checks,
generation tags, overflow retry and candidate-only CPU verification.

Five new CPU tests and six persistent-search tests pass. Mocked correctness and
same-nonce comparison CLI/reports pass. Isolated package tests pass. Actual GPU
execution now passes: all five large-grid cases and the same-nonce comparison.
Cache-excluded times: 1.043411s (64-query) and 0.389395s (4096-query).
No speedup claim until measured; no proof/share/service/clock change.


## v0.0.24-persistent-nonce-search

Twelve UTF-8 source files; unchanged GPU module and CPU library. NonceSearch
retains one candidate backend/cache across windows, preserving committed global
cursors and overflow retry behavior. Stale/error paths close the owned cache.
Six new CPU tests, four prior engine tests and a mocked eight-window CLI pass.
The isolated package tests also pass.

Next live check: 4,096 tiles, eight 512-tile windows, one nonce cache, actual
received target. Separate cache/window wall times will identify the next search
bottleneck. No new proof test, share submission, service or clock change. Live
multi-window GPU execution now passes: 4096 tiles in 1.086s, 64 batches, eight
windows and one cache. No full nonce or throughput claim.


## v0.0.23-live-search-worker

Twelve UTF-8 source files; reuse the existing PTX and CPU library. Single search
thread, one-slot latest-job mailbox, stale-result discard and joined shutdown.
Receiver remains active while preparation/GPU stages run. Five new concurrency
tests, five receiver tests and a mocked CLI/report smoke pass.

The new rig check attempts a fresh production-sized live nonce and 16 GPU tiles
at the actual received target. One pool connection, 180-second receive window,
with possible extra shutdown wait for an in-flight native commitment. No proof
build, share submission or service/clock changes. Assigned extranonce is a
provisional worker-nonce input for this experiment, not a verified submit rule.
Live execution now passes: fresh production commitments/seeds and 16 GPU tiles
at the actual received target, followed by joined shutdown. No full nonce,
accepted custom share or speed claim.


## v0.0.22-job-driven-search

Eight UTF-8 source files; no new binary or compiler. New job-driven engine uses
PoolJob profile/target, explicit caller-supplied nonces, streamed commitments,
the existing candidate-only GPU backend and independent PlainProof construction.
Native preparation and GPU results are gated by current job identity/generation.
Target replacement rejects the old preparation/search/proof stages.

Four new CPU tests and a CPU-emulated fresh synthetic path pass locally.
The new 160x192 V3 synthetic-session integration now passes GPU/official CPU
verifier execution on the rig. No network, service changes or share submission in this
check. Full production nonce completion, live nonce mapping and accepted custom
shares remain unvalidated.


## v0.0.21-live-job-receiver

Distribution: [source-file manifest](releases/pearlhash-dev-v0.0.21-files.json).
Seven UTF-8 Python files include the pool package and existing transport codec;
reuse the verified v0.0.17 CPU sources and v0.0.16 CPU library. No new GPU binary,
compiler/toolkit or opaque archive. Live reception now passes on the rig.

One explicitly configured TCP endpoint, one login, bounded framed reads, current
job callbacks and guaranteed session invalidation at connection end. There is
no submit method, hidden fallback endpoint or automatic reconnect. The runner
loads the user's wallet from its existing local independent-login transcript,
uses a separate diagnostic worker label, accepts an explicitly supplied V3/rank128
mining profile and stops after the first ready job or its receive deadline.
Only lengths/counts/target-bit-widths go into the report; no credential, header,
job key, token or assigned nonce is printed or stored in that report.

Five new CPU socket/stream tests pass, plus the preceding five session tests.
Fragmented/coalesced frames, truncated/invalid frames, size/message budgets,
job replacement, callback failure, cancellation before connection, timeout and
EOF all exercise closure/stale-work invalidation. Isolated seven-file package
checks pass. A mocked-socket CLI/report smoke succeeds without exposing its
synthetic wallet. These are not real network or pool verdicts.

The rig check made one login-only connection to pool.pearlhash.xyz:9000
and passed with fresh messages and a 224-bit scaled target. No GPU, commitments,
proof verification, mined/submitted share or service/clock changes. Extranonce's
compact-submit role and broader protocol rules still require verification.


## v0.0.20-pool-job-state

Distribution: [source-file manifest](releases/pearlhash-dev-v0.0.20-files.json).
Five UTF-8 Python files include the complete pool package needed by this step;
reuse the verified v0.0.17 CPU reference sources and v0.0.16 CPU hash library.
No new GPU module, compiler installation or opaque package is required.

Explicit V3 dense/rank128 profile validation, mining-config serialization,
header/config job-key derivation, non-saturating scaled share-target checks and
login/extranonce/notify job gating are implemented. Every notify/extranonce update
invalidates prior generation handles. Connection reset removes prior identity
and work. Unsupported markers, malformed notifications and zero/overflowing
share targets reject rather than continuing old work. Snapshot checks are not
an atomic network submission gate; no socket or share-submitting client is added.

Five CPU tests pass, including all six handshake orderings, changed-header vs
opaque-data behavior, target/extranonce replacement, reset/close/rejected login,
profile limits and target overflow boundaries. Isolated source-package tests and
a synthetic CLI-path smoke check pass with Python site packages disabled. The subsequent real rig
saved-context/login integration passes all new checks (three inbound handshake
messages), including replay key/bound match and replacement/reset invalidation. The runner reuses the
completed private replay's facts and independent login transcript without
rebuilding commitments, GPU work or proofs. Nothing private is distributed.

The terminal metadata inspection completed; neither raw nor either XOR view
contains an exact verified configuration match. This does not establish what
the retained bytes mean or require inferring config from them. The new path uses
an explicit verified profile. Metadata/token meanings and assigned-extranonce
mapping to submit worker_nonce remain unproven. No live pool job execution,
submitted/accepted custom share, full production nonce or performance claim.


## v0.0.19-candidate-only-search

Distribution: [source-file manifest](releases/pearlhash-dev-v0.0.19-files.json).
Only three new UTF-8 Python files; reuse the verified v0.0.17 PTX/source,
v0.0.18 global-index planner and existing v0.0.16 CPU hash library. No new
native binary, compilation or toolkit is needed.

The new search path stops computing CPU references for unsuccessful GPU tiles.
Returned complete candidates still require independent scalar CPU math and
already-scaled target checks. A structural queue decoder rejects bad lengths,
counts, overflow flags, duplicate/unknown slots and stale generation tags.
Partial queues cannot deliver candidates; the range scheduler retries them.
Missed GPU hits cannot be detected by this path alone, so the bounded correctness
runner separately compares all hit sets against full CPU references.

Four new CPU tests pass; the five preceding scheduler CPU tests also pass.
CPU-only integration prepares 64-query and production-shaped two-query cases
across seven target/queue scenarios each, then constructs a fresh synthetic V3
proof using the candidate-path global scheduler. GPU and official verifier were
not run on the development host. The rig runner will exercise the new GPU dispatch
and verify its NEW V3 proof using the existing official offline CPU oracle.
The subsequent RTX 5060 run passes all new GPU cases and official offline
verification of the fresh V3 proof: 64 search tiles, 13 returned candidates
CPU-checked. Earlier completed proof/capture tests are not rerun. No full production nonce,
live pool submission, custom accepted share or performance improvement is claimed.


## v0.0.18-global-range-batches

Distribution: [source-file manifest](releases/pearlhash-dev-v0.0.18-files.json).
Requires the existing verified v0.0.17 source/PTX directory and v0.0.16 CPU
library. Only three new UTF-8 Python files are downloaded. No new GPU module,
native binary, toolkit or compressed archive is required.

Global batches preserve periodic row-major tile IDs while removing the legacy
shared 32-row/column pool limit. Up to 64 independent global queries use one
noise cache across batches/retries. CPU references still check every tested tile.
Generation checks discard stale in-flight results before candidate delivery and
leave the cursor resumable. This is an offline synchronous scheduling harness,
not live pool cancellation or a complete production nonce search.

Five new CPU tests pass. CPU-only integration passes 130 small-domain tiles in
64/64/2 batches, plus two production-shaped tiles across a row-pattern boundary.
It checks complete-result overflow retry, cancel/resume, stale discard/resume,
cache lifetime and global candidate IDs. The subsequent RTX 5060 run passes
both GPU integration checks with completion saved.
No new proof check is required for this host batching change; the preceding
v0.0.17 fresh V3 proof already passed on the rig. No pool connection or gain claim.


## v0.0.17-virtual-fragment-cache

Distribution: [source-file manifest](releases/pearlhash-dev-v0.0.17-files.json) and
[readable sm_120 PTX](releases/pearlhash-dev-v0.0.17-sm120.ptx).

Manifest SHA-256: `2ab175ecf311bb7ab7aa35fbe31fbae547740dac8b6069602957cd8c2b10a183`.
PTX SHA-256: `1265a107fc0d98250179ab3c8097c7811f857a3d29ca3f0e296cda01cf62d704`.

This release distributes ordinary UTF-8 source files and actual compiler-generated
GPU PTX assembly. The NVIDIA driver loads/compiles PTX for sm_120; no CUDA/Rust
kit is installed on the rig. Reuse the existing verified v0.0.16 CPU hash library.
No compressed archive or new opaque native binary is distributed for this version.
The manifest binds every download path, size and SHA-256. Total file downloads
are 402320 bytes across 37 text files, including the 249357-byte PTX module.

Global uniform/permutation tables feed exact signed-byte MMA fragments without
materializing/uploading signal/noised matrices in the virtual scan. Constant fill
and final A-row nonce tail are retained. Table payload is capped at 64 MiB; the
production-shaped synthetic profile uses 34472080 payload bytes, plus keys,
guards/dispatch/driver resources. Byte accounting is not a memory benchmark.

One shared body implements virtual/materialized MMA, transcript, digest, target
comparison and tagged queue. New tests cover virtual bytes, global rows,
rank32/128/1024, signed fills, padding, repeats, eight warps, counter limits,
equality/overflow/tags/guards and a fresh virtual-path V3 proof. Seven production
tile queries are checked, not a full nonce. Primitive shapes are math tests,
not assertions of consensus-valid configurations. One original-wrapper regression
checks the shared-body refactor. CPU references make this a correctness harness.

63 development CPU tests pass / two prior oracle/vector cases skip. Source/PTX
standalone CPU-only preparation passes; it explicitly reports GPU unchecked and
official verification not run on the development host. The subsequent RTX 5060
run passes driver-JIT GPU checks, the materialized-wrapper regression and a fresh
virtual-path V3 proof accepted by the official offline CPU verifier. Prior
v0.0.16 V2/V3 nonce proofs also passed there.
No full production search, pool submission, measured gain or working-miner claim.


## v0.0.16-fresh-nonce-proof

Download: [Linux x86_64 / sm_120 fresh synthetic nonce-to-proof pipeline](releases/pearlhash-dev-v0.0.16-linux-x86_64.tar.gz).

SHA-256: `85d3944824e61b619793a93abb69fb81fa31d328304f3268cdf8cd020bf8602d`.

Connects synthetic header/config -> job key -> nonce tail -> streamed full
commitments -> explicit V2/V3 seeds -> GPU range candidate -> independent
PlainProof -> existing official CPU verifier. Seeds are derived from the actual
nonce-dependent commitments rather than supplied arbitrarily. B commitment
cache is keyed to the job; A commitment changes with the nonce. Generation,
nonce, math, target, root, seed and pattern bindings are checked before encoding.
Local synthetic context is saved for reproducibility; no captured data is used.

The fixed synthetic m=n=128/k=4096/rank=128/8x8 profile uses nBits0x1e100000:
base2^236 scaled by2^18 gives2^254, without saturation. This is actual target
filtering, not maximum-bound all-hit testing. Search stops after the first
completed batch with a candidate; at most three nonce attempts per explicit
V2/V3 context. It is not a general pool configuration/target/version decoder.

60 CPU tests pass / two prior oracle/vector tests skip. Roots and selected
proof encodings match full materialized CPU trees; stale/cache/nonce/target
bindings reject. CPU-only preparation finds both V2/V3 candidates and builds
proofs. The subsequent rig run passes GPU search and official CPU verification
for both fresh V2/V3 proofs. The development host has no Rust compiler or oracle. The existing rig oracle
will verify newly generated proofs; its old fixtures are not rerun/downloaded.

No new native compilation: unchanged v0.0.14 sm_120 cubin and v0.0.11 CPU library.
The v0.0.15 range scheduler passed its rig checks. No full production nonce loop,
pool client/share submission, performance result or working-miner claim.


## v0.0.15-periodic-range-scheduler

Download: [Linux x86_64 / sm_120 periodic range scheduler](releases/pearlhash-dev-v0.0.15-linux-x86_64.tar.gz).

SHA-256: `9265a7b1ad2bff70f22f948ddb22d7c936b78b41d2bb1698f3de8b5e5a5de433`.

Adds random-access periodic tile domains, global-to-local bounded batch mapping,
a resumable in-memory cursor, generation checks before launches/retries/delivery,
and overflow retry before committing results. No full matrix is allocated or
full index list enumerated. Signal/noise inputs are retained across retries and
released at the next batch. Callback failure leaves the batch cursor unadvanced.

The harness uses synthetic constant-signal profiles and supplied seeds. It
checks 15 small-domain tiles, including a nonce-derived tail and cancel/resume,
then two tiles each at the start/middle/end of an 8388608-tile domain with
m=5121/n=262144/k=32768/rank=128 and 10x16 patterns. Only six production-domain
tiles are tested: no full-domain or nonce completion claim. All tested GPU
digests/transcripts are compared with CPU references; maximum synthetic bounds
force candidate and overflow paths. This is not a performance benchmark.

57 CPU tests pass / two prior oracle/vector tests skip. Domain offsets match
brute-force checks; batching, coverage, stale cancellation, retry, delivery failure
and signal/tail bounds pass. Reuses the unchanged v0.0.14 native sm_120 cubin,
which passed five hardware batches /200 tile-target-queue checks on RTX 5060.
No new CUDA compilation. The subsequent rig run passes cancellation/resume,
all 15 small-domain tiles and all six production-domain window tiles.
No pool listener, externally atomic submission gate, persistent miner state,
full nonce search or custom share acceptance. Existing miners/clocks unchanged.


## v0.0.14-bounded-tile-scan

Download: [Linux x86_64 / sm_120 bounded GPU tile scan](releases/pearlhash-dev-v0.0.14-linux-x86_64.tar.gz).

SHA-256: `ff7f8b17770516e413f6df839a70dbdbfe94d467344bc3274ba7e929704790b8`.

Adds batched selected-tile evaluation over shared GPU-generated signed matrices.
MMA accumulators remain in registers; warp/block reduction folds rank prefixes
inside the kernel. Keyed digest and caller-supplied already-scaled u256 bound
comparison also run there. Normal output is a compact, generation-tagged
candidate queue, without global prefix-product arrays or prefix downloads.
A correctness-only optional audit saves 16 transcript words per tile.

The atomic queue counts every hit, flags overflow (including zero capacity),
and refuses to treat partial results as complete. CPU decode rejects duplicate,
unknown, stale or digest-mismatched records. The runner tests four synthetic
input batches plus an optional local saved replay input. Each uses five maps
and eight target/queue scenarios, including equality, adjacent bounds, misses,
mixed hits, zero/one-slot overflow, padding, repeated slots and eight warps.
These general math cases do not imply consensus-valid tile configurations.

Native sm_120 compilation succeeds; 53 CPU tests pass / two prior oracle/vector
tests skip. The unchanged native comparator matches Python integers for 1144
boundary/random pairs. The earlier v0.0.13 combined noise-to-MMA component
passed all four GPU cases on RTX 5060. The subsequent scanner test passes
all five batches / 200 tile-target-queue checks, including the saved replay input.
No full nonce/job search, inferred target scaling, pool submission, measured
performance or working-miner claim. Private session values are not bundled.


## v0.0.13-noise-to-mma

Download: [Linux x86_64 / sm_120 GPU noise-to-MMA component](releases/pearlhash-dev-v0.0.13-linux-x86_64.tar.gz).

SHA-256: `2d36c470f9ff22a8a0620279c939aec6bbe3cd6918a5d468cf53a661f935ce3e`.

Generates per-side reusable uniform/permutation tables and signed noised bytes
on the GPU, then feeds those device buffers directly to the exact integer MMA
kernel. Noise seeds, selected indices and signal bytes remain supplied inputs.
Each table hash produces 32 uniform bytes or eight permutation pairs. CPU
noised matrices are used for comparison only, never uploaded to this path.

Checks every table entry, noised byte, rank-boundary product, transcript word
and digest, with output guards. Three synthetic cases cover ranks32/128/1024,
selected-index limits, repeated indices, padded tiles and transcript-slot reuse.
An optional existing local PHGPU02 file reuses completed replay inputs without
rebuilding matrix roots or repeating the official verifier.

Native sm_120 compilation succeeds. Actual noise kernel bodies pass CPU
reference/guard checks; official-generated V2/V3 fixture noise/digests match.
50 development tests pass / two prior oracle/vector tests skip. The earlier
v0.0.12 MMA component passed all five cases on the RTX 5060. GPU execution of
this combined noise-to-MMA path now passes all four cases on the RTX 5060,
including the saved replay input. No private session input is bundled.
No search loop, custom share, pool verdict, benchmark or speed/power gain claim.
Existing miners/services/clocks remain unchanged.


## v0.0.12-integer-mma-check

Download: [Linux x86_64 / sm_120 integer tensor-core correctness component](releases/pearlhash-dev-v0.0.12-linux-x86_64.tar.gz).

SHA-256: `06a6a0b5261e4228dc6c3ee081f98d8b888148cc15dc4e39b170f3fd8f503853`.

Adds an independent exact int8-to-int32 cumulative matrix-product kernel using
NVIDIA's documented dense warp-level integer MMA layout. NVRTC 12.9.86 native
sm_120 compilation succeeds; own-code disassembly confirms IMMA.16832.S8.S8.
No FP8 conversion or saturation is introduced. Inputs are already-noised tiles.
Every rank-boundary product, transcript word and keyed digest is compared with
an independent scalar CPU reference, with guards around all output buffers.

Four synthetic cases cover signed extremes, one-hot/padded edges, multiple warps
and transcript-slot reuse. A bounded optional user-local PHGPU02 fixture reuses
the completed replay input, without rebuilding commitments or rerunning the
old verifier. No private session fixture/fingerprints/results are included.
A successful GPU run writes a local completion report. Three new CPU tests pass;
47 development tests pass / two prior oracle/vector tests skip.

All five tensor-core GPU cases now pass on the RTX 5060, including the local
10x16 / k=32768 / rank=128 input; all output guards remain unchanged.
No search loop, custom share, pool
verdict, hashrate/power measurement or speed improvement is claimed. The rig's
existing miner/services/clocks are left running and unchanged.


## v0.0.11-captured-share-replay

Download: [Linux x86_64 offline captured-share reconstruction](releases/pearlhash-dev-v0.0.11-linux-x86_64.tar.gz).

SHA-256: `6dd2cb196856df8e1f53f19e5de609d01fa4ed3b58f5db7c6cffdc5bafa675f4`.

Corrects the recorded profile's `sb` interpretation: wire value 1 is an enabled
flag, not literal matrix byte 1; the reconstructed signal fill is 64. A saved
existing-miner request matches its selected notification with V3 seeds and clears
the observed target under rank-128 scaling. This is one recorded profile, not
a general deployed-version rule or a new custom share.

New independent C++ streaming sparse Merkle construction hashes the complete
full constant-matrix commitments within the 8-GiB cap without full matrix/tree
allocation. Roots match a separate streaming BLAKE3 reference. Selected math
matches the independent C++ checker at 10x16, k=32768, rank=128. The independent
proof authenticates independently. Sparse opening serialization matches materialized CPU
trees for 16 odd/even/tail cases; native sanitizer bounds pass. 44 development
Python tests pass / two prior oracle/vector tests skip; three packaged tests pass.

New Linux CPU library/source included; no new CUDA compilation. The runner reads
the existing local capture with exact fingerprints, reconstructs the proof,
compares the existing GPU checker and invokes the rig's existing official CPU
verifier using the exactly representable recorded share target. Both GPU math and official CPU proof verification now
pass on the rig for the saved existing-miner replay. No pool connection, retransmission, custom share verdict,
working-miner or measured gain claim. Leave the working miners running.


## v0.0.10-gpu-leaves-to-proof

Download: [Linux x86_64 / sm_120 offline proof integration](releases/pearlhash-dev-v0.0.10-linux-x86_64.tar.gz).

SHA-256: `8b3a51967ea10cf4ecc0e694daf7406c2287358f3d0d38331f7cc908629cff50`.

Connects the rig-validated commitment kernel to fresh V2/V3 proof construction.
Leaf chunks run in bounded GPU batches; per-batch buffers are released. Parent
folds, seed derivation and Merkle openings use CPU code. All leaf/parent nodes
must match an independent CPU tree before proceeding to the existing GPU math
check and pinned official CPU verifier. Synthetic 128-row matrices only.

The commitment cubin and CPU hash library are byte-for-byte v0.0.9. The rig's
existing v0.0.5 math checker/cubin and v0.0.2 official verifier are reused.
Six packaged CPU tests pass, including proof-byte equality with the CPU pipeline
using an explicitly CPU-emulated leaf backend, odd trees/batch offsets and
corrupt-output rejection. Development suite: 41 pass / two prior tests skip.
No new development-host official-verifier execution or GPU run is claimed.

Both fresh V2/V3 integrated runs passed on the user's RTX 5060, including
GPU leaves, CPU parent comparison, GPU math and official CPU verification. This is not a
pool miner, production matrix reconstruction or accepted custom share, and no
speed/power claim is made. The runner makes no pool connection and changes no
service, clock or autostart setting.


## v0.0.9-commitment-leaf-check

Download: [Linux x86_64 / sm_120 keyed chunk-CV component](releases/pearlhash-dev-v0.0.9-linux-x86_64.tar.gz).

SHA-256: `95e444aaba0f8805b4e7a85fa7eb15d94fd37f3a3bf8bc8c301b0897e3b8ce4a`.

New independent keyed BLAKE3 full-chunk chaining-value kernel, compiled with
NVRTC 12.9.86 for native sm_120. 141 synthetic CPU CVs match the official BLAKE3
portable compressor at commit `f55849f89cd85083c1c9daa2c5de20766f309c00`.
CPU evaluation of the kernel body passes all comparisons, an empty launch and
output guards, including address/undefined sanitizers. Zero/FF data, nonaligned
launches, 64-MiB/8-GiB chunk-index boundaries, 32-bit carry and u64 maximum are
covered. These sparse indices do not hash a complete 8-GiB matrix.

CPU single-chunk CV hashing now accepts the full u64 counter; proof tree size
limits stay unchanged. Offline CUDA checks share one driver lifecycle helper.
The nonce kernel is unchanged. 38 Python CPU tests pass, two prior oracle/vector
tests skip; packaged three new tests and the CPU checker pass independently.

The user's RTX 5060 passed all 141 GPU CV comparisons and the empty launch,
with output guards and archive/internal checksums verified. No full GPU matrix
tree, resolved pool compact
reconstruction, accepted custom share or performance improvement is claimed.
This package makes no connection and changes no service or clock. Run the
included `tools/check_commitment_gpu.py` with the included CPU hash library.


## v0.0.8-nonce-tail-check

Download: [Linux x86_64 / sm_120 nonce-tail correctness component](releases/pearlhash-dev-v0.0.8-linux-x86_64.tar.gz).

SHA-256: `e27990499982940efe034f9bfdf7923d2802bb1d4c75c2696235d5d059d6ab2e`.

New independent nonce-tail arithmetic primitive, separate native sm_120 cubin,
Linux CPU kernel-body checker and stdlib-only GPU comparison runner. 25 CPU
protocol/nonce tests pass; 263 kernel-body CPU comparisons and output guards
pass. 32 synthetic cases agree with private arithmetic tracing; three trace
outputs are included as synthetic goldens. NVRTC/GCC compilation succeeds.

All 263 GPU comparisons passed on the user's RTX 5060 (sm_120), with output
guards unchanged and archive/internal checksums verified. This component makes no network
connection and changes no service or clock. Existing GPU math kernels are
unchanged. Complete captured-share reconstruction still does not meet the
target; this is not a working pool miner or accepted custom share. No gain claim.


## v0.0.7-protocol-development

Download: [Linux x86_64 / native sm_120 development package](releases/pearlhash-dev-v0.0.7-linux-x86_64.tar.gz).

SHA-256: `0cd95971e0964b628d5a4dafbbf4a2e69e506747c7e5dbf4414ad148eb97952a`.

Rebuilt independent CPU hash library, Linux GPU math checker and native sm_120
cubin. The library/cubin match v0.0.5 bytes; the rebuilt checker passes all
twelve CPU math inputs. New independent notify/header conversion, chronological
capture decoder and passive accepted-share-context collector are included with
source. 22 CPU protocol/header/context tests pass; 32 controlled inner-decoder
cases match. Extracted archive checksums and packaged CPU tests pass.

This is a development package, not a working pool miner. No new GPU run,
production matrix reconstruction, custom pool-accepted share or measured gain.
Existing completed rig checks need not be repeated for this protocol step.
The next necessary evidence is preceding notify candidate(s) and a later
accepted existing-miner submission. The included collector watches passively;
it sends no pool messages and changes no service or clock settings.


## v0.0.5-independent-proof

Download: [Linux x86_64 independent proof pipeline](releases/pearlhash-dev-v0.0.5-linux-x86_64.tar.gz).

SHA-256: `eb6161a69665c83edc7ff3cab5e158e6e1990ad972e4967e4f0f1419db13adb6`.

Adds independent native CPU commitment hashing, Merkle opening construction/
authentication, dense bincode proof encoding, and a fresh-candidate GPU-to-proof
runner. Newly constructed V2/V3 proofs pass the pinned official verifier on the
development host; ten official negative cases reject. Five proof tests pass;
original seed/math tests also pass with Python packages disabled. No pip/CUDA/
Rust installation on the rig. Reuses the already-validated v0.0.4 GPU checker
and cubin unchanged, plus the rig's existing v0.0.2 official CPU oracle.

Both fresh **V2/V3 GPU-to-proof runs passed on the user's RTX 5060**, with
archive/internal checksums verified; all 12 previous GPU math cases passed.
Synthetic easy-target fixed small jobs only. No live job decoder, production
search, share-submitting pool client, submitted/accepted share or measured gain. See
[independent proof scope and build instructions](proof/README.md).

## v0.0.4-gpu-noise-check

Download: [Linux x86_64 sm_120 noise/digest test](releases/pearlhash-dev-v0.0.4-linux-x86_64.tar.gz).

SHA-256: `07a714d4888de665aba3686d0c9e1d60049e32fd3d701f15806d943467532df7`.

Adds independent fixed-length keyed BLAKE3, deterministic noise generation and
final digest kernels. Native sm_120 compilation succeeds. All 12 CPU inputs
and 13 invalid-input cases pass, including host sanitizer checks. Five new
GPU noise/digest tests **passed on the user's RTX 5060**; the user also confirmed seven
v0.0.3 GPU matrix/transcript checks on the RTX 5060. Supplied seeds/indices;
no seed derivation, commitments, proofs, pool client, accepted shares or gains.
No compiler installation on the rig; no service or clock changes. See
[scope and rebuild instructions](gpu/README.md). Prior archives unchanged.

## v0.0.3-gpu-math-check

Download: [Linux x86_64 sm_120 offline math test](releases/pearlhash-dev-v0.0.3-linux-x86_64.tar.gz).

SHA-256: `6ec23dfacad5f753085140231dcd5f2262f4a0208a259430677c9da51ddc6249`.

Native sm_120 kernels compiled with NVRTC 12.9.86, plus a GCC 13.3 C++17 Linux
harness. Approximately 260 KiB compressed. No compiler installation on the rig.
Seven compact inputs; all cumulative products and transcript words are checked.
CPU reference checks and malformed-input rejection pass, including host
AddressSanitizer/UndefinedBehaviorSanitizer checks (leak detection disabled).
**All seven GPU tests passed on the user's RTX 5060; not a miner; no pool verdict or performance claims.**
No GPU noise/digest, Merkle proof construction or pool protocol implementation.
See [scope and rebuild instructions](gpu/README.md). Existing miners and clocks
are untouched. The v0.0.2 archive remains unchanged.

## v0.0.2-cpu-reference

Download: [Linux x86_64 CPU validation package](releases/pearlhash-dev-v0.0.2-linux-x86_64.tar.gz).

This is an offline CPU oracle/reference checkpoint, not a GPU miner. Includes compiled CPU verifier, source, official-generated V2/V3 synthetic fixtures, independent Python math checks, dependency notices, internal checksums, and the original standalone Git history bundle.

Archive SHA-256: `83083651ac353030caea92e8790149402184d639b34c7c54b950a1a17420aef6`.

Compiled and tested on the development host; the user confirmed both offline CPU fixtures pass on the Debian rig. No CUDA compilation, GPU test, custom-miner pool acceptance or performance gain is claimed. The ordinary CPU executable makes no network connections. Build dependency downloads are separate.

Validation: seven Python tests; Rust test covers both proof versions plus modified-header/opening rejection and a tiny-target rejection. Exact version behavior is checked against intermediate seeds/transcripts/digests; easy-target fixtures are not evidence of production mining performance.

The source under this subdirectory uses its own ISC license. No XMRig files or live rig settings are modified by this checkpoint.

