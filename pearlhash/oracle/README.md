# Offline official CPU oracle

This adapter links the official zk-pow crate at an exact Git revision to provide
a trusted CPU correctness baseline. It neither runs WildRig nor connects to a
pool. Our own GPU code must match the fixtures before submitting live shares.

## Build (Linux x86_64)

Requires a C/C++ build toolchain, make, Git, Rust/rustup and network access for
dependencies. rust-toolchain.toml selects Rust 1.99.1. From the project root:

```sh
cargo build --manifest-path oracle/Cargo.toml --release --locked
cargo test --manifest-path oracle/Cargo.toml --release --locked
```

Executable: `oracle/target/release/pearl-cpu-oracle`. Use the supplied standalone
binary on the rig; do not fill its small persistence with a full build toolchain.

## Generate and verify fixtures

```sh
oracle/target/release/pearl-cpu-oracle fixture 2 tests/vectors/official-v2.json
oracle/target/release/pearl-cpu-oracle fixture 3 tests/vectors/official-v3.json
oracle/target/release/pearl-cpu-oracle verify tests/vectors/official-v3.json
```

Generation uses seeded upstream try_mine_one, serializes the PlainProof,
deserializes it through the compatibility parser, calls the official plain
verifier, and exports selected matrix values, roots, seeds, noise, transcript
and digest. No ZK certificate is generated.

Input JSON requires cert_version, header_base64, plain_proof_base64 and optional
share_nbits. Extra fixture fields are ignored by the Rust verifier.
header_base64 is the official 76-byte incomplete header; share_nbits is a
compact target override and never replaces the header's committed nbits.

Certificate version is trusted external context, not guessed from PlainProof.
The synthetic easy target accepts every jackpot, so changing seed context alone
need not reject such a proof. Exact seed/transcript/digest comparisons test
version behavior instead. Neither fixture demonstrates live pool acceptance or
realistic share-finding performance.

This CLI reads local trusted fixtures. It has size caps but is not a hardened
network-facing parser. A future pool client must separately bound allocations,
parse structure and validate job context before verification.

## Build record

Rust 1.99.1, x86_64-unknown-linux-gnu, default portable target, release with
overflow checks. Host Ubuntu glibc 2.39. Runtime: libc.so.6, libgcc_s.so.1 and
the x86_64 ELF loader. Highest observed required GLIBC symbol version: 2.34.
No CUDA dependency. Cargo.lock is committed for dependency reproducibility.
