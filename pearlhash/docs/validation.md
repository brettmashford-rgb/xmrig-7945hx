# Validation and release gates

1. Pin authoritative sources. Confirm pool certificate/protocol context.
2. Run the official CPU verifier and relevant upstream tests. Produce fixtures
   containing header, config, matrices, roots, seeds, noise, transcript, final
   digest, target and encoded proof. Cross-check the independent CPU path.
3. Compile an sm_120 correctness kernel. Compare every intermediate stage with
   CPU goldens; cover partial tiles, signed values, accumulator/byte-order rules,
   changing jobs and boundary targets. Check memory usage fits 8 GB.
4. Implement the observed pool protocol. Verify candidates locally before
   submission. Record accepted/rejected/stale outcomes and job associations.
5. Only after real accepted shares: publish an experimental mining binary with
   architecture, compiler, runtime requirements, source commit and SHA-256.
6. Benchmark; profile; make one measurable change; repeat relevant validation.

## Sustained comparison

- Preserve existing WildRig binary and enabled pearl.service.
- Run the custom executable separately; no installer or autostart replacement.
- Use identical measured core/memory clocks, power limit, fan policy, driver,
  ambient conditions, and XMRig workload. Avoid competing GPU miners.
- Existing snapshots: 75.98 TH/s at 101.7 W/2497 MHz; 79.00 TH/s at
  117.9 W/2595 MHz; memory 810 MHz. They are user-reported short snapshots.
- Saved service core is 2500 MHz; last live core was 2600 MHz. Record actual
  state before a comparison; do not silently normalize it.
- Warm up to a stable temperature; compare at least 30-minute runs and enough
  accepted shares for uncertainty to be useful. Extend when share variance is
  large. Use an A/B/A sequence where practical.
- Log actual clocks, GPU power, temperature, elapsed time, attempted work,
  accepted difficulty-weighted work, rejects/stales and reconnects. State the
  exact PearlHash work accounting behind any TH/s number.
- Compare both device-reported work rate and pool accepted work per second.
  Difficulty changes require weighted accounting. Report sampling uncertainty.
- Report average GPU power separately from wall-system power. Compare useful
  work per joule; neither a short hashrate spike nor lower power alone is a gain.

## Current validation level

At v0.0.2, the official CPU PlainProof verifier accepts both generated offline
V2/V3 fixtures. Independent Python code matches their job keys, seeds, selected
noise matrices, full jackpot transcripts and digests. Negative tests cover
changed header, changed matrix opening, invalid signal, wrong seed context and
an intentionally tiny target. See README for the exact scope of each test.

At v0.0.3, native sm_120 kernels compile for cumulative products and the
transcript fold over pre-noised fixture matrices. Seven compact CPU checks and
malformed-input rejection pass. Host sanitizer checks pass with leak detection
disabled. The user has confirmed both v0.0.2 oracle fixtures on the rig.

At v0.0.3, GPU execution was pending and GPU noise/digest were not
implemented. See the newer checkpoint status below. Pool encoding remains unresolved. No custom live share submission
or speed/power improvement has been demonstrated. Offline validity is not pool
acceptance. See [GPU checkpoint scope](../gpu/README.md).

## Rig confirmation and next checkpoint

The user supplied a Termius screenshot confirming all seven v0.0.3 GPU
matrix/transcript tests passed on the RTX 5060 sm_120, with archive/internal
checksums OK. This does not validate noise, digest, proof construction or
pool compatibility.

At v0.0.4, independent fixed-length keyed BLAKE3 and noise code builds for
sm_120 and matches Python/official-generated outputs on the CPU. All 12
compact CPU cases and 13 invalid-input cases pass. New GPU noise/digest tests
remain pending. Noise seeds and row indices are still fixture inputs. No
seed derivation, commitment/proof construction, target handling or pool client
is added by this checkpoint. No accepted shares or performance gains.

## v0.0.4 rig result

The user's next Termius screenshot confirms the v0.0.4 archive and internal
checksums passed, GPU 0 was the RTX 5060 sm_120, and all five noise/product/
transcript/digest tests returned PASS. The shell returned normally. All 12
offline GPU tests across v0.0.3 and v0.0.4 are now confirmed on the rig.
The fixture seeds are still supplied; proof/commitment construction, pool
codec/client compatibility and real accepted shares remain unvalidated.
No new benchmark or speed/power gain is established by these tests.

The offline PCAP framing analyzer has four synthetic tests and reproduces both
preserved captures without TCP gaps or conflicting retransmissions. It is not
a codec or a source of job/target/proof/verdict semantics; see pool findings.

## v0.0.5 independent construction

Independent CPU commitment trees, Merkle opening generation/authentication and
explicit dense PlainProof bytes are now implemented. New signals use SHAKE256
rejection sampling; official try_mine_one is not used. Fresh V2/V3 proofs pass
the pinned external verifier, which rejects ten corresponding altered-leaf,
root, missing-sibling, changed-header and tiny-target cases. Original proof
bytes round-trip and openings authenticate. Five proof test methods pass;
seven old math/seed tests also pass through the new native hash fallback with
site packages disabled. Native hash sanitizer checks pass with leak detection
disabled due to host restrictions. Source/limits are in proof/README.md.

The v0.0.4 GPU checker/cubin are reused unchanged. The new runner asks them to
check a fresh candidate's complete selected math, then constructs its proof
and requires official verification. That two-version GPU-to-proof path is
now confirmed on the user's RTX 5060 for both V2 and V3, with archive/internal
checksums OK. CPU-only tests are explicitly labeled. The jobs are
synthetic/easy-target/fixed small dimensions, not current pool jobs. Pool codec,
live protocol/version context, submitted shares and performance remain open.


## Independent transport diagnostic

The outer codec now reproduces all eleven messages in the two preserved
captures. The captured acknowledgements correlate to login/report_info, not
share submissions. No captured submit or share verdict exists. A login-only
Python probe uses our own agent name and a distinct worker on the same pool.
It sends one login, waits at most 30 seconds / 16 messages, stores its transcript
locally with mode 0600, and disconnects after login/extranonce/notify. It does
not execute GPU work, submit shares, reconnect or touch services/clocks.
Five synthetic tests cover codec golden/round trips, malformed frames, fragmented
replies, successful login and rejected/truncated exchanges. Live independent
login is confirmed by the user's 2026-10-24 Termius screenshot: accepted login,
16-character extranonce, notify field lengths [400,64,16,1], PASS and normal
shell return. Source checksum also passed. The notify payload's separate scrambling, field semantics,
production search, submission and pool acceptance remain unresolved.


## Submission capture decoder

The new offline decoder uses independent outer decoding and TCP reassembly.
Five tests add connection/request-id isolation, negative/ambiguous responses,
partial/malformed frames and larger captured submissions. All fourteen pool
transport tests pass. It does not generate shares or open a pool connection.
The preserved old messages decode with zero submissions. Header research has
produced structurally plausible candidate bytes; the general inner codec,
job configuration/version semantics and independent submission remain open.


## Capture 04 rig result and pattern support

The user's screenshots confirm the capture decoder ran on 24 packets / ten
messages with verified sources, zero kernel-dropped packets, one existing-miner
submit and a matching true/status=1 response for id 866. This confirms an
observed successful WildRig submission, not custom-miner acceptance. Initial
mid-session boundaries are explicitly unverified. Full byte transfer is pending.

Independent PeriodicPattern byte parsing, canonical list reconstruction and
offset rules now cover the observed 10x16 tile shape, with a bounded expansion.
Three CPU test methods cover the existing fixture golden, the new relative
patterns at synthetic offsets, and invalid/noncanonical/oversized inputs.
The offline proof runner uses this helper for its existing unchanged pattern.
No new GPU or official-verifier execution was performed for this pattern-only
change. Full pool nonce/signal generation and current job binding remain open.

### Pool protocol continuation after capture 04 transfer

- Reconstructed complete capture 04: both rig-reported PCAP and gzip SHA-256
  match; independently reproduced submit id 866 and its true response.
- Ordered decoder confirms accepted submit before any notify in this capture;
  no share/header association is inferred.
- Independent first-stage notify header conversion matches 32 controlled
  pseudorandom complete-payload cases against the isolated legacy decoder.
  Target bytes copy exactly in these cases; comparison/scaling remains open.
- 22 CPU protocol tests pass, including ordered TCP availability, strict notify
  parsing and selection of preceding notify candidates with an accepted submit.
- No new GPU binary/test, live independent share or efficiency result in this
  change. Full pool compact matrix reconstruction remains to be validated.

### v0.0.7 Linux development package build

GCC 13.3.0 rebuilt the independent CPU hash library and GPU math harness;
NVRTC 12.9.86 compiled native sm_120 successfully without a GPU. Cubin and
CPU hash library SHA-256 match v0.0.5 exactly; rebuilt math harness differs
and passes all twelve existing CPU fixtures. 22 protocol/header/context tests
pass with Python site packages disabled, both before and after packaging.
The strict final decoder runs on verified capture 04. A synthetic local
capture-process lifecycle test stops its own process group and emits the
expected preceding-notify/accepted-submit context, without a network connection.
Archive and internal checksums verify after extraction. No new GPU execution
or live independent share is claimed for this build.

### v0.0.8 nonce-tail primitive

- Rig capture retained accepted existing-WildRig request 1161 and two preceding
  notify candidates. Rig SHA-256 comparisons confirm the transcribed decoded
  headers and canonical submission, without establishing header association.
- 32 synthetic input pairs match a private arithmetic trace of the inspected
  device nonce-tail primitive. Three public synthetic outputs are pinned in
  tests; these are not official published consensus full-proof goldens.
- 25 CPU protocol/nonce tests pass with Python site packages disabled.
- GCC 13.3.0 builds the Linux CPU kernel-body checker. All 263 inputs match the
  separate native CPU hash implementation, with output guards unchanged.
- NVRTC 12.9.86 compiles a separate native sm_120 nonce-tail cubin. GPU execution
  passed on the user's RTX 5060: all 263 comparisons match the independent CPU
  calculation and output guards remain unchanged. Archive and internal checksums
  verified on the rig. Neither the old GPU math kernel nor its completed rig tests change.
- The small archive includes component source, binaries, test vectors, build
  provenance and internal SHA-256 checksums. Extracted package CPU checks pass.
- Complete captured-share CPU reconstruction hypotheses still do not meet the
  target. No working pool miner, custom share acceptance or efficiency claim.


### v0.0.9 commitment leaf component

- Rig screenshot verifies all 263 v0.0.8 nonce-tail GPU cases and output guards;
  source archive/internal checksums match. This remains isolated arithmetic.
- Two more preceding captured headers (packets 15 and 35) transcribe exactly:
  their SHA-256 values match rig output. All four retained candidate headers
  still fail the current CPU compact-reconstruction hypotheses. No candidate is
  identified as the share's actual job; no extra capture was requested.
- New keyed full-chunk BLAKE3 CV kernel compiles with NVRTC 12.9.86, sm_120.
  141 synthetic native CPU CVs match official BLAKE3 portable C compression at
  f55849f89cd85083c1c9daa2c5de20766f309c00. This is a hashing oracle only, not
  the official Pearl verifier or a pool verdict. Official oracle source/binary
  stays on the development host; the distributed implementation is independent.
- Ordinary CPU evaluation of the kernel body matches all 141 CVs and preserves
  guards, including empty-launch behavior, zero/FF blocks, nonaligned thread
  counts, index 65535/65536, the 8-GiB chunk boundary, 32-bit counter carry and
  the u64 maximum. Address/undefined sanitizer checks pass (leak checks off).
- A standard BLAKE3 two-chunk root golden independently checks the CV/root flag
  distinction. Three new Python tests pass without Python extensions.
- Development Python suite: 38 pass / two skip (prior official verifier and
  unavailable original JSON vectors). The independent Python BLAKE3 dependency
  is supplied on the development host for the old hash/tree comparison test.
- Native CPU single-chunk counter support expands to u64; existing tree-size
  and proof-size bounds remain. The old nonce kernel is unchanged; its runner
  shares an extracted CUDA lifecycle helper. CPU nonce comparisons still pass.
- Actual new GPU execution remains pending. No complete large matrix root,
  current-pool reconstruction, custom share submission/acceptance or measured
  speed/power claim. Existing rig mining is left in place.


### Rig-confirmed v0.0.9 and v0.0.10 proof integration

The user's screenshot 1792834907985.jpeg confirms archive/internal checksums,
all 141 keyed chunk CV comparisons, the empty-launch case and unchanged output
guards on sm_120. The runner also passed the two-chunk root-domain golden gate.
This is isolated commitment-leaf GPU evidence, not a complete matrix-tree proof.

The v0.0.10 source connects those leaves to bounded commitment trees. Each batch
is at most 128 KiB by default; device buffers are released after every batch.
Every tree node must match a complete CPU reference tree before seed derivation.
GPU noise/products/transcript/digest, independent CPU openings/serialization and
the pinned official CPU verifier then run on freshly generated V2/V3 candidates.
Parent folds and seeds remain CPU work; matrix inputs retain the 64-MiB cap.

Six packaged CPU tests pass. Three new integration tests cover uneven batches,
odd trees, padding and one-chunk root distinction; reject malformed/corrupt CVs;
and compare complete V2/V3 proof bytes and math inputs with the existing CPU
pipeline using an explicitly CPU-emulated leaf backend. They do not execute a
GPU or the official verifier. The development suite passes 41 tests and skips
two prior tests (missing local official verifier and original JSON vectors).
The extracted package verifies and repeats its six CPU tests successfully.

New integrated GPU execution/official verification is pending on the rig. The
commitment cubin/library are unchanged from v0.0.9; the rig's existing v0.0.5
GPU math binary/cubin and v0.0.2 pinned verifier are reused. Full current-pool
compact reconstruction remains unresolved. No custom share, accepted pool
verdict, speed/power result or working-miner claim.


### Rig-confirmed v0.0.10 and local captured-share reconstruction

The user's screenshots confirm fresh V2 and V3 GPU-leaf-to-proof integration on
RTX 5060, checksum verification, all 256/512 leaves per synthetic matrix matching
CPU trees, GPU math/digests passing, and both proofs accepted by the official
CPU verifier. Seed derivation, parent folds and openings are CPU work.

The observed supported signal mode uses the `sb` field as an enabled flag,
with constant fill 64, rather than a literal fill byte. This corrected model
reconstructs a saved existing-miner case below its selected share target with
explicit V3 seeds. It is evidence for that supported case, not a general rule
for future deployed pool versions. Private record selectors, fingerprints,
nonces and derived values are read/generated locally; none are bundled here.

Independent C++ sparse Merkle construction streams both complete commitments
without allocating the full matrix or CV tree. Development roots agree with a
separate streaming BLAKE3 implementation; selected math agrees with the separate
C++ CPU checker. Constructed sparse openings authenticate independently. The
user-local share target is converted to nBits only if exactly representable;
the original header is not modified. The saved replay has now passed GPU math and official CPU proof verification
on the rig, with package checksums verified and a completed local manifest.

Small sparse opening bytes match materialized CPU trees in 16 odd/even/tail
cases, including the one-chunk ROOT distinction. Corrupt openings, malformed
requests, profile misuse and inexact share targets reject. Native output guards
and address/undefined sanitizers pass (leak checks disabled). 44 development
Python tests pass / two old oracle/vector tests skip; three packaged tests pass.

Materialized trees retain the 64-MiB bound. Constant sparse openings support at
most 8388608 chunks, 4096 selected leaves and 65536 siblings; proof parsing stays
capped at 8 MiB. The generic replay has no network or share-submission code.
No custom share, production search, new pool verdict or measured gain is claimed.


### v0.0.12 independent integer MMA kernel

The rig's completed v0.0.11 local manifest reports GPU math checked and official
CPU verification passed for the saved existing-miner replay. No replay process
remains running. This confirms offline reconstruction; it is not a new submitted
or accepted custom share. No root/proof stage needs repeating for this milestone.

New dense integer MMA code uses the NVIDIA-documented m16n8k32 register layout,
signed byte inputs and int32 accumulators, preserving every rank-boundary prefix.
Zero padding handles incomplete 16x8 subtile edges. A separate launch folds the
transcript and computes the keyed BLAKE3 digest. NVRTC 12.9.86 compiles native
sm_120; inspection of the project's own binary confirms IMMA.16832.S8.S8.

Three new CPU tests validate known signed-prefix values, cumulative persistence,
one-hot edge cases, slot reuse and bounded/corrupt local-file rejection. The
49-test development run passes 47 / skips two prior oracle/vector tests. The
new CLI prepares four synthetic scalar comparisons and optionally the LOCAL
completed PHGPU02 replay fixture. Every prefix product is checked, so XOR-only
permutations cannot hide a layout bug. Product/transcript/digest outputs carry
poison guards, and allocations are freed per case. Packaged tests/checksums and
CPU-only completion-report behavior pass. No private fixture or results are
bundled. A report marks GPU checked only after all actual GPU checks pass.

The MMA GPU execution subsequently passed all five cases below. There is no scalar GPU fallback,
new noise/seed/commitment implementation, production search or benchmark here.
No working independent pool miner or measured speed/power gain is claimed.

The v0.0.12 tensor-core check now passes on the RTX 5060 for all four synthetic
cases and the local saved 10x16 / k=32768 / rank=128 input. Every prefix product,
transcript word and digest matches the CPU reference, and guards are unchanged.
This validates the integer MMA component; no search, custom share or measured gain.

## v0.0.13 GPU noise tables into integer MMA

The new component generates uniform rows, per-side permutation pairs and signed
noised matrices with separate ordered GPU launches. The resulting device
buffers feed the existing tensor-core kernel directly. Each table element and
noised byte is checked with independent scalar noise; all rank-boundary products,
transcript and digest are checked with the scalar matrix reference. Output
guards cover uniform, permutation, noised, product, transcript and digest buffers.

The new source compiles natively for sm_120; own-code disassembly includes the
same dense integer MMA instruction. CPU execution of unchanged noise kernel
bodies matches the CPU reference with guards intact for rank32/128/1024,
repeated/near-limit row indices and partial launch blocks. This is not GPU
execution or GPU scheduling emulation. Official-generated V2/V3 fixture inputs
reproduce their saved matrices, transcript and digest. Corrupted local fixture
seeds, signals, indices and digests reject. 50 tests pass / two prior
oracle/vector tests skip. The CLI prepares three synthetic cases and the local
completed replay input successfully in CPU-only mode; that report correctly
marks GPU unchecked. The subsequent RTX 5060 run passes all four combined
noise-to-MMA cases: all tables, bytes, prefixes, transcript, digest and guards
match, including the saved 10x16 / k=32768 / rank=128 input.

The earlier standalone MMA path passed on the rig. No GPU seed derivation,
commitments, production search, target filtering or pool submission is added
here, and no performance result is claimed. Private inputs stay local.

## v0.0.14 bounded GPU tile scanner

The scanner evaluates caller-selected row/column maps from the same device
noised buffers. All eight warps participate in block barriers; inactive and
padded lanes contribute zero. At each rank boundary, lane/warp folds update
the shared 16-word transcript. The keyed digest and little-endian u256 <= test
run in the same kernel; the bound must already include caller-established
configuration/rank scaling. The pinned official sanity checks use <=; this
primitive does not implement the remaining consensus rules or infer scaling.

Only hits enter a bounded atomic queue with tile ID, u64 caller generation and
digest. The total includes hits beyond capacity, and an explicit overflow flag
causes the host's completeness check to reject partial results. The decoder
checks unordered hit sets, digests and generation tags. Optional audit output
contains transcript words only; no prefix arrays are allocated or downloaded.

New CPU tests cover 1144 actual-comparator comparisons against Python integers,
known scalar tile results, duplicate/reversed maps, stale/unknown/corrupt records,
invalid descriptors/bounds and zero/one-capacity overflow. The 55-test development
run passes 53 / skips two prior oracle/vector cases. CPU-only preparation succeeds
for all four synthetic batches and the existing local replay fixture. This does
not execute GPU barriers, shuffles, MMA or atomics. Native sm_120 compilation and
own-code disassembly succeed. The subsequent RTX 5060 run passes all five
batches /200 tile-target-queue checks, including the saved replay input.
Digests, transcript audit, generation tags and guards match.

The rig runner will compare five tile maps across eight target/queue scenarios
per input batch, including a 32x32 eight-warp math case. Synthetic tile shapes
and duplicate indices are general math tests, not assertions of consensus validity.
No new capture, root rebuild, proof regeneration or pool operation is needed.
Earlier v0.0.13 GPU noise-to-MMA checks already passed and are not rerun as a
separate milestone. No full nonce/job range scheduler or live cancellation is
implemented; generation tags alone are not job cancellation. No custom pool
share or throughput/power improvement is claimed. Private inputs stay local.

## v0.0.15 periodic range scheduler

Mixed-radix valid-offset indexing matches brute-force periodic offset checks for
single, two/three-dimensional, non-unit-gap and large-gap patterns. Domain
construction is constant-size and random access logarithmic/constant in pattern
digits; no matrix-wide index list is built. The observed 10x16 shaped domain at
m=5121/n=262144 contains 512 x 16384=8388608 tiles. The planner maps row-major global
IDs into local pools bounded at 32 selected rows/columns and 64 queries per batch.

A resumable in-memory cursor advances only after complete validated results and
synchronous candidate callback delivery. Generation is checked before launches,
retries and delivery. Partial queues are discarded and retried at full batch
capacity. Controlled cancellation discards the current uncommitted batch and
allows resume without duplicate committed tiles. Delivery/backend failures leave
that cursor unadvanced; callbacks must be idempotent if they fail after effects.
These are scheduling hooks, not a live pool listener or atomic submission gate.

57 CPU tests pass / two prior oracle/vector tests skip. New tests cover exact
small-range coverage, first/middle/last maps of the large domain, overflow retry,
cancel/resume, stale-result discard, failed delivery and constant-profile limits.
The unchanged rig-validated v0.0.14 cubin is reused, with no new CUDA compilation.
CPU-only integration passes 15 small-domain and 6 production-domain tiles. Actual
GPU scheduler integration subsequently passes on RTX 5060, including cancellation/
resume and all 21 tested tiles. The full production range is not scanned.

The next rig harness uses synthetic supplied seeds and maximum already-scaled
bounds for all tested candidates. It compares all tested digests/transcripts
with CPU references and retains device inputs across retries. It neither loads
private capture data nor regenerates commitments/proofs. No full nonce loop,
header-bound seed builder, live job client, submitted share or measured gain.

## v0.0.16 fresh synthetic nonce/range/proof binding

The new runner creates a fresh synthetic incomplete header and fixed 52-byte
configuration, hashes the job key, streams complete constant B and nonce-tailed
A commitments, derives explicit V2/V3 seeds, and feeds the existing GPU range
backend with an actual non-maximal scaled target. B commitment cache is tagged
by job key and reused across same-job nonce attempts. This is a fixed synthetic
profile, not inferred live pool rules. Header nBits0x1e100000 ->2^236; rank128
is neutral and 8*8*4096=2^18, so the bound is2^254 without saturation, matching
the pinned proof_utils/sanity_checks arithmetic. It is not general target logic.

A target-meeting candidate must match generation, selected scalar math, nonce
tail, recomputed commitment roots, explicit derived seeds and job patterns.
Independent streamed openings form a dense PlainProof that round-trips and
authenticates locally. The rig runner invokes the existing official CPU verifier
with the synthetic header target and saves completion only after both V2/V3
positive checks succeed. It does not rerun old fixtures or contact a pool.

60 CPU tests pass / two prior oracle/vector cases skip. New streamed roots and
selected openings match separate full materialized trees; changed nonces alter
A roots/seeds, same-job B root is stable, V3 seed salt differs, stale caches and
candidate bindings reject. Non-maximal bound filtering, misses and queue retry
work in the CPU backend. CPU-only V2/V3 search/proof preparation succeeds and
marks GPU unchecked / official verifier not run. No development-host Rust/oracle
executable is available. The subsequent rig run passes the new GPU/oracle
integration for both fresh V2/V3 proofs (8 and 4 tiles scanned respectively).
The old CUDA binary/CPU library bytes are unchanged. The full upstream ZK suite
has not been run, and this Python path is not a complete consensus validator.

Full efficient production nonce search, live job/cancellation/submission logic
and real custom pool acceptance remain unimplemented/unproven. No hashrate,
power, speed improvement or working-miner claim. Existing services/clocks stay.

## v0.0.17 virtual signed-byte fragment cache

The new input representation stores complete global uniform/permutation noise
tables and the 16-byte A tail, then builds exact signed-byte fragment words on
demand. No signal/noised matrix is allocated or uploaded by the virtual scan.
A shared device template preserves the existing MMA/fold/target/tagged-queue
body for both original and virtual inputs. Global descriptors are bounded at
32 rows/columns per tile and 64 queries per launch; total table payload <=64MiB.
The production-shaped synthetic profile has 34472080 table payload bytes. Keys,
guards/descriptors and driver resources are additional; no memory benchmark.

CPU tests execute the actual uniform-generation kernel body and virtual loader,
not GPU ISA/scheduling. Counter carries/upper bound and guards match independent
CPU hashes; every selected signed byte matches scalar noise for positive/zero/
negative fills, repeated/reversed rows, rank32/128/1024, padding and final A tail.
Global descriptors beyond32, cache cap and fresh V3 nonce/proof preparation pass.
65 tests run: 63 pass / two prior oracle/vector cases skip. Native NVRTC 12.9.86
sm_120 compilation succeeds and own-code disassembly contains integer IMMA.
New virtual GPU execution remains pending; CPU preparation is explicitly flagged
GPU unchecked / official verifier not run on this host.

The rig harness will compare all small-domain virtual input bytes, sample the
large domain's first/middle/last rows, compare all used global uniform rows and
every permutation pair, then compare tile transcript/digest/candidate queues with
CPU references. Three cache profiles cover 14 tile queries across six target/
queue scenarios each, including overflow zero/one and equality. Only seven
production-domain queries are checked, including the final nonce row. No full
production nonce is searched. Debug probe output and one materialized-wrapper
regression are diagnostic allocations; they are not the virtual scan's input
representation. Each cache owns/releases only its own buffers, including across
errors; the harness checks that all allocations are released.

A fresh synthetic V3 nonce/proof then uses the virtual backend and existing
pinned official CPU oracle. CPU commitments, tail, seeds, references and proof
encoding remain CPU work. This new GPU/oracle combination is pending on rig;
the previous v0.0.16 fresh V2/V3 proofs already passed. No pool connection or
custom share, no throughput/power comparison and no working-miner claim.

### v0.0.17 source/PTX delivery

The distributed module is readable UTF-8 PTX 8.8 targeting sm_120, generated with
NVRTC 12.9.86 compute_120 from the same virtual-input CUDA source. The native
cubin build exists on the development host, but is not part of this distribution.
No opaque compressed package or new native binary is published. All 37 source/
PTX downloads are individually listed with byte sizes and SHA-256 in a public
manifest. The existing verified v0.0.16 CPU library is reused on the rig. No
CUDA/Rust toolkit is installed there. cuModuleLoad accepts a PTX file and the
driver compiles it for the GPU; actual driver-JIT execution is pending on rig.
Standalone source/PTX CPU-only preparation passes with GPU unchecked and official
verification not run. That is not a GPU result or a pool verdict.



### v0.0.17 RTX 5060 confirmation

User-supplied terminal output confirms all 37 source/PTX files and the existing
CPU library verified, then the sm_120 driver loaded/JIT-compiled the PTX.
The three cache profiles passed 67584, 14336 and 196608 signed-byte probes,
respectively, plus 4/3/7 tile queries across six target/queue scenarios each.
Tables, transcripts, digests, tags and guards matched the CPU references.
The original materialized-wrapper regression passed. A newly generated
virtual-path V3 proof was accepted by the official offline CPU verifier.
Completion was saved on the rig. This supersedes the pending hardware status
above; it is not a pool verdict, full production search or measured gain.

## v0.0.18 global-index range batches

GlobalRangePlan preserves the original domain's row-major IDs and creates only
one bounded batch at a time. Each tile carries its own global rows/columns, so
the former batch-wide 32-row pool restriction is unnecessary for virtual inputs.
GlobalBatch is a separate type: the new backend rejects legacy local-pool batches.
The unchanged virtual kernel still caps each tile at 32 rows/columns, each launch
at 64 queries and each cache payload at 64 MiB. CPU references remain mandatory
for every tile, including misses; no faster unchecked search path is introduced.

Five new CPU tests cover lazy batch sizes/ordering, production-sized boundary
maps compared with the original index planner, invalid indices/types/intervals,
overflow retry, failed-delivery cursor preservation and local/global ABI rejection.
CPU-only integration also passes 130 small tiles in 64/64/2 batches and two
production-shaped tiles across an A-pattern row boundary. All-hit maximum bounds
intentionally force overflow/retry; they do not model pool difficulty. Controlled
generation changes test cancellation after a committed batch and after an
in-flight result. Stale results cannot deliver or advance the uncommitted cursor;
resuming the original generation completes that interval. A cache is retained
through retries and released at test end. Callbacks retain the existing idempotency
requirement when they raise after side effects.

No CUDA compilation was needed; the rig-validated v0.0.17 PTX is reused unchanged.
New GPU integration is pending. The runner records complete only after all new
checks pass, and CPU-only mode explicitly records gpu_checked=false. No new
commitment/proof/capture test is repeated. No live pool connection, custom share,
full production nonce or throughput/power improvement is claimed.


### v0.0.18 RTX 5060 confirmation

The user-supplied completed Termius output confirms previous source/module/library
checksums and both global scheduler GPU cases pass: 130 small-domain tiles in
64/64/2 batches and two production-shaped row-boundary tiles. CPU references,
overflow retry, global IDs, stale in-flight discard and resume all matched.
Completion was saved. This supersedes the pending v0.0.18 GPU status above.

## v0.0.19 candidate-only CPU validation

CandidateScanner invokes the unchanged virtual_tile_scan entry with transcript
audit disabled. It uploads descriptors/targets, not CPU noised matrices or CPU
tile results. Cache generation remains on GPU. A new decoder validates exact
queue/status lengths, total<=query_count, overflow==(total>capacity), unique valid
query slots, full u64 generation tags and inclusive already-scaled u256 bounds.
Only complete queues are independently recomputed on CPU using global_reference;
zero-hit queues do no candidate reference work, and partial queues retry without
validating/delivering a truncated set. Device output/cache guards still check.
No table CPU-reference scan is performed before every search batch. No claim
is made that this path independently detects GPU false negatives.

The separate test harness computes all references outside CandidateScanner, then
compares complete hit sets for 64 global singleton queries and two 10x16/k32768
production-shaped queries. Seven scenarios cover all-hit, no-hit, mixed, inclusive
equality, digest-minus-one and capacity-one/zero overflow. It checks the exact
number of returned-tile CPU verifications, including zero for misses and partial
queues. CPU emulation must compute all references to emulate the GPU; that is
explicitly not a GPU/candidate-only-work result. Four new CPU unit tests cover
unordered complete hits, no-call empty/partial paths, malformed lengths/counts/
flags/slots/tags, duplicate records, equality and independent math rejection.
The prior five global scheduler tests also pass. The standalone version-overlay
imports and new four tests pass with Python site packages disabled.

Fresh synthetic V3 nonce search now uses GlobalRangePlan plus CandidateBackend;
returned global IDs feed the existing nonce/header/root/seed/pattern/proof checks.
The existing official offline verifier will check this new path's fresh proof.
CPU-only preparation passes (64 tiles scanned to first completed hit batch),
with GPU unchecked and official verifier not run. New GPU execution and official
proof verdict remain pending on the rig. The GPU module bytes are unchanged.

This remains a synchronous offline search integration, without full production
nonce completion, live pool version/config/target rules or share submission.
No comparative timing, hashrate, power, efficiency or working-miner claim.


### v0.0.19 RTX 5060 confirmation

The completed user terminal output confirms both candidate-only GPU dispatch
profiles pass all seven queue/target scenarios, with complete hit sets matching
the separate full CPU test references. No-hit/partial-queue paths perform zero
candidate recomputations. Fresh V3 candidate-path search scanned 64 tiles and
CPU-checked 13 returned candidates; the new independent proof was accepted by
the existing official offline CPU verifier. Completion was saved. This supersedes
the pending v0.0.19 GPU/oracle status above. Counts are not a performance benchmark.

## Remaining pool metadata inspection

The first 76 bytes of the notify payload have a verified header conversion;
the remaining 124 bytes still have no established field interpretation. The new
inspect_job_metadata.py reads the existing local context bound to the already
completed captured-share replay manifest. It compares retained metadata tails
across saved notifications and shows raw/two repeating-XOR candidate views
against the verified 52-byte replay config. Those views are explicitly
unverified hypotheses, not a protocol implementation or inferred configuration.
The tool makes no connection and does no GPU/proof work. Headers, wallet, worker/
miner nonces and private capture fingerprints are not printed or distributed.
Session-specific input/output remains on the rig and in the user's terminal.


### Saved metadata inspection outcome

The user completed the inspector after the installer was corrected to include
its own pool decoder instead of assuming the v0.0.17 source manifest included
that package. No previous GPU/proof test failed. Raw/two repeating-XOR views
show no exact 52-byte config match. These unsuccessful views do not establish
a decoder or prove the retained bytes carry that configuration.

Reference CPU setup inspection copies 76 header bytes and assembles 52 config
bytes separately from dimension/rank/pattern parameters. This observation does
not establish every pool payload field or handshake rule. The independent job
state therefore accepts an explicit profile and retains all other payload/token
bytes as opaque. It does not guess their meanings or discard their identity:
every incoming notification invalidates the preceding generation.

## v0.0.20 explicit pool profile/job-state binding

MiningProfile supports the currently implemented V3 dense constant-bias64/tail1
path, rank128, complete 1024-byte chunk rows, k2048..65536, canonical even-sized
patterns up to32 rows/columns, tile32..256 elements, worker input<=4MiB, matrix
streaming<=8GiB per side, dimensions<=2^24 and virtual noise table payload<=64MiB.
These are intentionally narrower implementation limits. The upstream pinned
sanity_checks.rs and pearl_program.rs define TILE_H=2 and validate public-proof
shapes. The config is k(u32), rank(u16), Int7 MMA(u16=0), two six-byte patterns,
then32 zero dense bytes. Job key hashes header76+config52 with independent BLAKE3.

Rank128 is neutral for the pinned rank penalty, so share bound is rawLEtarget *
rows.size * cols.size * k. It must be positive and fit u256. This follows the
upstream mining-share penalized_target_bound behavior, which rejects overflow;
it deliberately does not use the saturating consensus-nBits helper. This is a
policy/configuration adapter, not a complete consensus validator or inferred
live deployment/version rule. The caller must explicitly configure V3; marker2
and any unsupported message/profile reject.

PoolSession publishes an immutable job only after accepted login, valid eight-
byte assigned extranonce and supported notification exist. All six input orders
are tested. Each notification/extranonce update invalidates previous generations;
target updates preserve the header/config key but change the bound. Opaque
metadata/token changes still invalidate the prior handle. Reset clears login,
assigned identity and active/pending work. Invalid notifications cannot retain
active work; rejected login closes the session. Lock-protected snapshot checks
are not an atomic share send gate. Assigned extranonce is not yet asserted to
be the submit worker_nonce, and notify token is not asserted to be a job ID.

Five new CPU tests pass, plus synthetic saved-input CLI integration and altered
bound rejection. The isolated five-file source package passes those tests and
CLI smoke check with site packages disabled, including its own pool/__init__.py
and job.py. No new native or CUDA compilation. The actual rig check is pending:
compare derived key/bound with the already-completed private replay, then feed
its separate independent-login transcript through the new state machine and
exercise controlled target replacement/reset. It does not mix identities across
those two sessions, rebuild proofs/matrices, use GPU or contact a pool. Reports
explicitly say GPU=false, proof-verifier=false and live-connection=false.

Remaining metadata meanings, live identity/submit integration, full production
search and real custom pool acceptance remain unproven. No performance claim.


### v0.0.20 rig saved-message confirmation

The completed user terminal output confirms all five source checksums and all
saved-input checks pass. Explicit profile/header derive the completed replay's
job key and scaled share bound; the separate independent-login exchange builds
a ready snapshot from three messages. Controlled target replacement and reset
invalidate stale work. No connection, GPU or proof work occurred. This supersedes
the pending saved-input status above; unknown nonce/token/metadata roles remain.

## v0.0.21 bounded live-job receiver

PoolReceiver consumes strict newline/ASCII-hex outer frames through the existing
independent codec, then feeds the validated messages to PoolSession. FrameBuffer
handles split nibbles/newlines and multiple frames in a read; oversized complete/
unfinished frames, invalid decoding and truncated EOF reject. Reads and total
message/byte budgets are bounded. One explicit endpoint is connected and one
login is sent; transport nonces are not mining nonces. No alternate endpoint,
automatic reconnect or submit capability is present. An RLock-protected session
provides job snapshots; callbacks must publish quickly rather than blocking
receipt on GPU/commitment work. No atomic network-send gate is claimed.

Every run resets the old identity/work first. Every connection end or exception
closes the session, invalidating its active job. Controlled tests cover one-
endpoint/one-login behavior, fragmentation/coalescing, repeated job callbacks,
callback failure, pre-connect cancellation, read timeout/deadline, EOF, malformed/
truncated frames and message/size budgets. Five receiver CPU tests and five prior
session tests pass. The isolated seven-file source package passes its five new
tests with site packages disabled; a mocked-socket CLI smoke confirms its report
does not contain synthetic wallet credentials. No real network/GPU run on this
host, and no new native/CUDA compilation is needed.

The live runner reads the already saved successful login's wallet locally, uses
a separate diagnostic worker label, and receives at most one ready job under an
explicit V3/rank128 profile. It reserves a mode0600 result file before connecting,
never records credentials/raw sessions, and stores only readiness, lengths,
counts/generation and target bit width. It exits on the first ready snapshot or
its bounded receive window, then checks no active work remains after closure.
Actual pool execution of this new receiver is pending on the rig. Login/job
reception is not a submitted/accepted share, proof or mining performance result.


### v0.0.21 rig reception result

The completed user-provided output confirms seven source checksums, fresh pool
login/extranonce/notify, current job creation with a 224-bit scaled target, and
active-work invalidation after disconnect. No GPU work, proof or submitted share.

### v0.0.22 job-driven engine

Four CPU tests cover explicit dimensions/nonces, incompatible base rejection,
job replacement during native preparation, replacement during GPU dispatch,
search-window coordinates, actual job target propagation and backend cleanup
when cache setup becomes stale. The local CPU-emulated 160x192 V3 synthetic
session completes independent proof construction and three stale-stage gates.
No local official verifier or GPU execution is claimed. The rig runner will
exercise the same new engine through the validated PTX and existing official
CPU verifier, with fresh small synthetic inputs and no network/submission.

Native commitments are synchronous and cannot cancel mid-call. Job checks
discard stale output between stages; the receiver and engine are not yet joined
by a live worker thread. Caller-supplied worker nonce does not establish the
assigned-extranonce/compact-submit mapping.


### v0.0.22 rig result

The completed user-provided output confirms eight source checksums, fresh
160x192 V3 job-driven GPU search/proof, official offline CPU verifier acceptance,
and rejection of stale nonce/search/proof stages after target replacement.
No connection or submitted share in this synthetic integration.

### v0.0.23 concurrency and bounded live runner

Five deterministic tests check latest pending replacement, in-flight stale result
discard, close/current-state cancellation and joining, worker-error propagation,
receiver progress during blocked search, single-login stream lifecycle, and
settings/start guards. All five receiver tests pass with the extended maximum
receive window (300 seconds). A mocked CLI smoke checks worker-thread context
ownership, joined lifecycle, redacted report and zero submissions. These local
checks do not execute an actual GPU or network connection.

The rig runner keeps its receiver active while production commitment preparation
and a 16-tile GPU window execute. It preserves the actual target and records
component wall times, not throughput. Native stages are finite but not mid-call
cancellable, so shutdown may outlast the receive deadline. No proof generation
or submit path. Provisional assigned-extranonce use does not prove the live
compact-submit nonce mapping. Live GPU execution remains pending.


### v0.0.23 rig result

Completed user output confirms fresh pool job -> production commitments/seeds ->
16 GPU tiles at the actual received target, then receiver closure, worker join
and active-job invalidation. Component wall times: B commitment 29.404s, nonce
preparation 0.583s, bounded scan 0.074s. Existing miners were running; these
measurements do not establish full-nonce throughput. No share was submitted.

### v0.0.24 persistent cache/window checks

Six CPU tests cover exact cursor continuity across windows, one backend creation
and idempotent close, overflow retry without cache recreation/duplicate hit,
replacement between windows, dispatch failure preserving the last committed
cursor, setup-time replacement cleanup, and clamping/empty windows at the
domain end. Four prior engine tests still pass. Isolated package tests pass.
A mocked CLI/report smoke checks eight windows, 64 dispatches, one cache and
joined shutdown/redaction; this is not real network/GPU execution.

The new rig runner uses 4,096 production tiles in eight windows, preserving
one live-job nonce cache and the actual target. Cache setup and each window
are timed separately. No proof rebuild or share submission; existing miners
and clocks stay unchanged. Actual multi-window execution awaits the rig.


### v0.0.24 rig result

Completed user output confirms all twelve checksums and 4096 live-job production
tiles across 64 batches/eight windows with one cache. B preparation 29.425s,
nonce 0.573s, bounded scan 1.086s, cache setup 0.049573s. Receiver closure,
worker join and invalidation pass. No submitted share or full nonce measurement.

### v0.0.25 larger dispatch

The pinned original virtual_tile_scan/tile_scan_core sources use query_count
and capacity parameters with blockIdx.x global descriptors, without a 64-query
GPU limit. The old 64-query bound is enforced by host validation/packing. The
new path reuses the established descriptor serializer in chunks and expands
bounded host-side target/queue handling to 4096. No PTX recompilation/patching.

Five CPU tests cover the maximum descriptor payload, unordered complete queues
with slot4095, malformed count/overflow/tag/duplicate/bound cases, strict caps,
production row-boundary mapping, wide-plan engine injection and overflow retry
preserving global hit IDs above63. Six prior persistent-search tests still pass.
Isolated package tests and two mocked CLI/report smokes pass. No local GPU or
network execution is claimed.

The rig diagnostic independently computes four small query references and
checks five large-grid/queue scenarios, including all 4096 hits and partial
queues. It deliberately repeats those four queries to keep independent CPU work
bounded; this is not full independent recomputation of 4096 distinct production
tiles. The subsequent live comparison uses both dispatchers on the same nonce/
target, with one fresh cache per path and window times excluding setup. Equal
early-candidate results are checked; common kernel faults are not excluded by
that same-kernel comparison alone. Larger-batch GPU execution/performance is
pending the rig. No share submission or broader throughput claim.


### v0.0.25 rig result

User output confirms fourteen checksums and all five GPU wide-grid queue cases,
including 4096 complete hits, empty/overflow queues and a 67-query partial grid.
The same-nonce production comparison passes. Cache-excluded times: 1.043411s
for 64 launches versus 0.389395s for one 4096-query launch. B preparation 29.436s,
nonce 0.570s, new bounded scan including cache 0.436s, cache setup 0.045167s.
This is component timing under concurrent existing mining, not miner throughput.

### v0.0.26 per-warp kernel

The new kernel retains exact signed-int8/int32 MMA accumulation, prefix XOR/
rotate transcript and keyed digest/target/queue behavior. It computes each
query's up-to-eight MMA subtiles within one warp. All lanes participate in
shuffle reductions/gathers; transcript slot i is retained by lane i. Partial
grids return only whole inactive warps; there are no cross-warp barriers.

NVRTC 12.9.86 produced real UTF-8 PTX8.8/sm120. An independent invocation of
the published build helper reproduced identical bytes; generated new-entry
PTX contains zero block barriers. Eight inherited GPU files were restored and
verified against the pinned v017 manifest before compilation. No vendor binary
or compiler is distributed.

Two CPU tests check coverage for partial/full warp grids and the 20-argument
host ABI/audit allocation contract; five prior wide tests pass. Mocked CLIs
check report/lifecycle and all twenty intended scenarios with CPU references;
these are not GPU executions. The real rig diagnostic must match independent
CPU prefix transcripts and digests for ranks32/128/1024, one/two/four/eight
MMA-subtile layouts, padding, signed values, nonce tails, max/equal/below bounds,
complete/overflow queues and high generation tags, with guards unchanged.

The live comparison is gated on diagnostic success and uses both compiled
kernels from the new module on the same nonce/target, one cache per path.
Actual GPU correctness and speed remain pending; no proof/share verdict.
