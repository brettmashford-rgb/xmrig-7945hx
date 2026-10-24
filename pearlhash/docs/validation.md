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
