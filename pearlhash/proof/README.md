# v0.0.5 independent PlainProof construction

Fresh matrices -> commitments -> derived noise seeds -> GPU math check ->
independent Merkle openings/PlainProof serialization -> official CPU verifier.
This is an offline construction pipeline for synthetic jobs, **not a miner**.
No live job decoding, pool submission or accepted custom-miner share exists.

## New implementation

- `blake3_cpu.cpp`: independent CPU BLAKE3 chunk chaining values, parent/root
  compression and one-chunk hashing, exposed through a small C ABI library.
  CPU proof hashing is separate from the validated GPU hash implementation.
- `reference/native_hash.py`: ctypes adapter; no Python extension ABI or pip
  package is required on the rig. The existing math reference falls back to
  this backend when the Python blake3 package is unavailable.
- `reference/plain_proof.py`: independent commitment trees, multi-leaf opening
  generation/authentication, and dense bincode-1 PlainProof parsing/serialization.
- `tools/offline_end_to_end.py`: generates fresh signal matrices, builds roots,
  derives V2/V3 seeds, computes a CPU comparison and asks the existing native
  sm_120 checker to validate every selected noised value, cumulative product,
  transcript word and digest byte. Only after that GPU check passes does it
  construct/emit a PlainProof and call the pinned official verifier.

The official generator `try_mine_one` is not called. The official verifier is
an external correctness oracle, not the proof builder. Source authority remains
commit `82e6eee7076aafe10123e08db78f100d270c0582`, specifically
`pearl-blake3/src/{hasher,merkle}.rs`, `zk-pow/src/ffi/plain_proof.rs`,
`zk-pow/src/ffi/mine.rs`, and seed/config/header serialization sources.

## Scope and limits

The runner generates synthetic easy-target headers and fixed small dense jobs:
m=n=128, rank=128, k=2048 (V2) / 4096 (V3), selected rows/columns
0,1,8,9,64,65,72,73. SHAKE256 supplies reproducible signal randomness through
rejection sampling over [-64,64]; it does not replace consensus hashing.
It does not parse arbitrary jobs or search production-difficulty targets.
This is proof construction validation, not a useful mining workload benchmark.

CPU commitment input is capped at 64 MiB, chunk indices at 65535, proof inputs
at 8 MiB. Dense proofs only; no MoE. The Merkle authenticator is not a complete
consensus verifier. Target and all remaining verification rules are checked by
the official oracle, which remains mandatory for this runner.

GPU cubin and math executable are byte-for-byte copies from v0.0.4, whose
five new GPU cases passed on the user's RTX 5060. No GPU source/kernel was
changed by this checkpoint. Both **fresh V2/V3 candidate-to-proof GPU runs
passed on the user's RTX 5060**, including official offline verification.
Archive/internal checksums also passed. Old fixtures were not replayed.

## Run on the rig

From the extracted v0.0.5 package (keep the existing miners running):

```sh
python3 -S -m tools.offline_end_to_end \
  --oracle /home/user/pearlhash-dev-v0.0.2/bin/pearl-cpu-oracle \
  --output-dir ./run
```

The output directory must not already exist. The runner writes two fresh GPU
inputs, two independently constructed verification JSON files and a manifest
containing the random seed, roots, digest, hashes and validation stage results.
The same seed can be supplied with `--seed` (64 hexadecimal digits).
No network connections, service changes, clock changes, CUDA/Rust installation
or Python package downloads. The prior v0.0.2 oracle is reused without change.

## Build and scoped validation

GCC 13.3.0, Linux x86_64 baseline, no host-specific ISA flags:

```sh
mkdir -p bin
g++ -std=c++17 -O3 -Wall -Wextra -Werror -shared -fPIC \
  -fvisibility=hidden proof/blake3_cpu.cpp -o bin/libpearlhash.so
```

The library requires system libc; its C ABI is independent of Python version.
The reused checker needs the same driver/libstdc++ runtime as v0.0.4.

Five proof test methods pass on the development host:

- Native keyed/unkeyed small hashes and even/odd tree roots match the independent
  Python blake3 library, including root/chaining-value distinction.
- Original official-generated V2/V3 proof bytes round-trip exactly, and their
  A/BT Merkle openings authenticate independently.
- Newly constructed V2/V3 proofs pass the pinned official verifier. Ten negative
  official-verifier cases reject altered leaves/roots, missing siblings, changed
  headers and tiny-target attempts.
- Independent Merkle authentication rejects five corruption variants.
- Dense parsing rejects truncation, trailing bytes, MoE tags and oversized counts.

The original seven math/seed tests pass with Python site packages disabled,
exercising the native fallback. The standalone runner's two fresh CPU-only
proofs pass official verification. Native hashing also passes address/undefined
sanitizers (leak detection disabled due to host process-inspection restrictions).
No full upstream ZK/circuit suite, new GPU run, pool verdict or benchmark is
claimed. The earlier 12 offline GPU cases remain confirmed on the rig.
