# PearlHash development checkpoints

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
verifier using the exactly representable recorded share target. Those two new
rig stages are pending. No pool connection, retransmission, custom share verdict,
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
