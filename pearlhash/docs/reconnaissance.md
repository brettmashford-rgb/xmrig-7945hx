# Source inspection — 2026-10-23

## Authority and reproducibility

Repository: https://github.com/pearl-research-labs/pearl
Commit: `82e6eee7076aafe10123e08db78f100d270c0582`.
All paths below refer to that commit. A shallow checkout was inspected locally;
upstream build scripts and downloaded miner binaries were not executed.
Root license: ISC; preserve notices and check subproject/dependency licenses.

## What exists

| Component | Authoritative source | Finding |
|---|---|---|
| CPU mining reference | `zk-pow/src/ffi/mine.rs::try_mine_one` | Random signed matrices, commitments, deterministic noise, incremental matrix products, jackpot transcript and proof construction |
| CPU plain-proof verifier | `zk-pow/src/api/verify.rs::verify_plain_proof` | Parses proof; checks constraints, value ranges, noise/GEMM jackpot, difficulty and rank penalty |
| Seed versions and goldens | `zk-pow/src/api/seed.rs` | Explicit legacy/salted selector and pinned dense/MoE outputs |
| Header/config encoding | `zk-pow/src/api/proof_utils.rs` | Field-by-field wire encoding; must not serialize native structs |
| Header types | `zk-pow/src/api/proof.rs` | 76-byte incomplete header; 52-byte mining configuration |
| Noise | `zk-pow/src/circuit/pearl_noise.rs` | Keyed BLAKE3 deterministic low-rank noise and sparse permutations |
| Jackpot transcript | `zk-pow/src/ffi/mine.rs`; `zk-pow/src/circuit/pearl_program.rs` | Cumulative products reduced at rank boundaries; 16 u32 words; rotate-left 13 then XOR |
| Final jackpot hash | `zk-pow/src/api/proof_utils.rs::compute_jackpot_hash` | Keyed BLAKE3 of 16 little-endian u32 transcript words |
| Proof encoding | `zk-pow/src/ffi/plain_proof.rs` | Bincode PlainProof; compatibility path for old missing MoE tag; Merkle openings required |
| Difficulty | `zk-pow/src/api/sanity_checks.rs` | Little-endian 256-bit jackpot, work/config scaling and rank-penalty rules; not a generic nonce hash check |
| CUDA reference | `miner/pearl-gemm/csrc/` | CUTLASS mining infrastructure; setup.py sets compute_90a/sm_90a; no verified sm_120 build |
| Reference gateway | `miner/pearl-gateway/src/pearl_gateway/miner_rpc/` | JSON-RPC 2.0 getMiningInfo/submitPlainProof infrastructure; not evidence of Pearlhash port 9000 wire format |
| Tests/fixtures | `zk-pow/src/api/seed.rs`, `zk-pow/src/circuit/compat_test.rs`, `zk-pow/fixures/` | Seed goldens, circuit compatibility tests and binary STARK fixtures exist; no verified complete pool job→accepted-share golden assembled yet |

## Version rules matter

`node/chaincfg/params.go` mainnet settings at this commit:

- MoE/V2 cutover: height 71,935.
- Dense-only softfork: height 91,630.
- Rank-penalty softfork: height 96,251; minimum rank 128 in current verification.
- Salted-seed/V3 cutover: height 99,000.

These are inspected source settings, not a live query of the pool's deployed
software or current chain tip. Confirm the pool's job context explicitly.
V3 salts matrix roots and binds dimensions before deriving noise seeds.
Using a legacy implementation unconditionally would be incorrect after cutover.
The inspected MMA enum contains Int7xInt7ToInt32. No FP8 algorithm change is
inferred from third-party posts or search snippets.

## Pool protocol: unresolved

https://pearlhash.xyz/ advertises pool.pearlhash.xyz:9000 and a TLS endpoint at
9443, and recommends WildRig. That establishes endpoint configuration, not
subscribe/authorize, job fields, share encoding, or difficulty semantics.
No Stratum implementation or mining.subscribe/mining.notify/mining.submit
matches were found in the inspected official checkout.

Do not assume Bitcoin Stratum or transplant another pool's dialect. Needed:

1. Actual handshake and job messages from the working WildRig connection.
2. Source of certificate version (field, protocol agreement or verified pool rule).
3. Exact header byte order, share target representation and scaling.
4. Share submit envelope, proof encoding, successful reply and rejection replies.
5. Job replacement/clean-jobs semantics, difficulty updates and reconnect behavior.

A passive capture can preserve the existing miner, but first check available
tools. Large proof payloads may require a full capture rather than terminal
screenshots. Capture only the configured pool connection; do not log unrelated
traffic. Do not send invented shares. A live transcript confirms observed
behavior and still needs independent cryptographic verification.

## What is missing from this project

- GPU correctness tests and the complete upstream ZK/circuit test suite.
- Live pool-derived fixed jobs/proofs. Offline official-generated V2/V3 fixtures
  and independent noise/transcript/digest comparisons now exist (v0.0.2).
- Confirmed Pearlhash protocol adapter and accepted-share transcript.
- sm_120 CUDA implementation, compiler toolchain and GPU correctness runs.
- Sustained benchmarks and profiling evidence.
- Hosted project remote and compiled GPU miner releases. v0.0.2 includes only
  an offline CPU oracle executable.

## Feasibility

Public reference code makes independent implementation technically plausible.
The official CUDA path cannot be assumed portable from sm_90a to sm_120.
Beating WildRig's already optimized kernel 2 is unknown; only identical-clock,
sustained accepted-work measurements can establish a gain.
