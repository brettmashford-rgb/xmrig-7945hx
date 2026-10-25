# Public miner source review, 2026-10-25

This review informed an independent kernel experiment. No external miner source
or binary was imported into the ISC implementation, and no pool was changed.

## Open Pearl Miner / Neil-linked source

The Neil announcement linked `neilquicks/neil-pearl-miner` (404 at review time).
`neilquicks/open-pearl-miner` returned GitHub 451 with a DMCA notice pointing to
Muskwak's original repository. The original source was available at:

- https://github.com/Muskwak/Open-Pearl-Miner/tree/ac3d992d7eb6ca1bb344d5d3ee125eecb182248d
- https://github.com/Muskwak/Open-Pearl-Miner/blob/ac3d992d7eb6ca1bb344d5d3ee125eecb182248d/LICENSE

The custom licence's condition 2 requires published derivatives to retain its
2% developer fee. Its personal-use exemptions do not grant fee-free public
redistribution. Consequently none of its miner code was copied. Its README
claims fused tensor-core GEMM/transcript/noise generation and a LuckyPool client;
those claims are not measurements on our GPU or proof of Pearlhash-pool support.

## Akoya reference miner

Reviewed tree: `akoyapool/akoya-miner@0e42b2a50b4cb62cb8995b77420226c2182137ce`.

- `native/pearl-gemm/csrc/blackwell/transcript_gemm_sm120.cu`: dedicated SM120
  consumer lane, a 128x256 GEMM block, shared input stages and asynchronous
  copies. This is a larger cooperative compute unit than our isolated 10x16
  search query. The compute block and proof-pattern dimensions are distinct.
- `src/Akoya.Miner/Mining/GpuWorker.cs`: resident B state, two work streams,
  prepared graph state and a separate B-Merkle build/copy path.
- `proto/v2/miner.proto`: gRPC registration, streamed jobs, vardiff messages,
  server-issued B seeds and full share submissions. This is not the framed
  JSON protocol at the currently configured Pearlhash endpoint.
- No repository-wide licence file was found in the reviewed tree; API licence
  metadata was null. No Akoya source was copied.

https://github.com/akoyapool/akoya-miner/tree/0e42b2a50b4cb62cb8995b77420226c2182137ce

## Other candidates

`egg5233/tw-pearl-miner` had documentation/packaging rather than reusable GPU
kernel source in the reviewed tree. `blindrun/soat-miner` was MIT-licensed, but
its current README supports Ergo and did not supply a compatible Pearl path.
The research miner linked by arXiv:2606.04819 was not publicly retrievable at its
advertised GitHub URL at review time. None was treated as validated rig software.

Official Pearl source at `0798903bced203de8cfcb49441f44fd9b51b18eb` has an ISC
root licence with separately licensed subprojects. It remains an authoritative
protocol/proof reference. The existing pinned verifier was not silently updated.

## Applied change

The independently written cooperative kernel shares K128 inputs across 16
existing 10x16 search queries in a 2-by-8 grid, with two asynchronous input stages.
This retains our current nonce/profile/transcript/target semantics, rather than
copying a different miner's 128x256 proof layout or its pool client. Shared tiling
and software pipelining are general CUDA techniques described by NVIDIA:

https://docs.nvidia.com/cutlass/latest/media/docs/cpp/efficient_gemm.html

Next validation compares all transcripts and complete/overflow candidate sets
against independent CPU math, then rotates equal-work comparisons between the
old virtual kernel, isolated fragment cache and cooperative kernel. No actual
GPU speedup or accepted custom share is established by the source review.
