# PearlHash development checkpoints

## v0.0.4-gpu-noise-check

Download: [Linux x86_64 sm_120 noise/digest test](releases/pearlhash-dev-v0.0.4-linux-x86_64.tar.gz).

SHA-256: `07a714d4888de665aba3686d0c9e1d60049e32fd3d701f15806d943467532df7`.

Adds independent fixed-length keyed BLAKE3, deterministic noise generation and
final digest kernels. Native sm_120 compilation succeeds. All 12 CPU inputs
and 13 invalid-input cases pass, including host sanitizer checks. Five new
GPU noise/digest tests are **pending**; the user has already confirmed seven
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
