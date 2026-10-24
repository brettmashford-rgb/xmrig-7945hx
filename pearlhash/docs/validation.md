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
own-code disassembly succeed; actual scanner execution remains pending on rig.

The rig runner will compare five tile maps across eight target/queue scenarios
per input batch, including a 32x32 eight-warp math case. Synthetic tile shapes
and duplicate indices are general math tests, not assertions of consensus validity.
No new capture, root rebuild, proof regeneration or pool operation is needed.
Earlier v0.0.13 GPU noise-to-MMA checks already passed and are not rerun as a
separate milestone. No full nonce/job range scheduler or live cancellation is
implemented; generation tags alone are not job cancellation. No custom pool
share or throughput/power improvement is claimed. Private inputs stay local.
