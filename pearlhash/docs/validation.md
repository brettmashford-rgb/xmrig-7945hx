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
