# PearlHash architecture targets

Updated 2026-11-12 from the rig's V080 and V081 completion screenshots. This is the ordered backlog for larger changes; completion means measured rig evidence, not just implemented code.

| Order | Target | Mechanism | Status | Evidence required |
| --- | --- | --- | --- | --- |
| 1 | Compute-layout redesign | Rebalance row/column ownership and input reuse across warps while controlling accumulator registers. | V081 completed. Pair-direct retained: 2,326,001 tiles/s, 84.20 W, 27,737 tiles/J. The 8x4 layout lost 9.9% throughput; 4x8 lost 29.0%; both were less efficient. All had 96 registers/thread, zero local bytes and two active blocks/SM. Broader cooperative redesign remains open. | Identical transcripts and canonical coverage, independent CPU/V3 proof checks, equal-work speed, native resources and full-nonce board energy. Retain control unless median elapsed improves >3%. |
| 2 | Multi-nonce B reconstruction reuse | Share reconstructed B fragments during scanning across distinct A/nonces for the same job, beyond existing per-job B tables. | V082 first two-nonce experiment implemented; GPU results pending. Compares unchanged pair-direct with matched 512-thread private/shared B variants, preserving 32 tiles per nonce per CTA. | Distinct nonce bindings, per-nonce transcripts/hits, exact coverage, cancellation and ownership, memory footprint and total unique work/s including setup. B already has substantial reuse across rows; do not assume another factor-of-two saving. |
| 3 | Native dispatch / CUDA Graphs | Reduce Python/driver work, batch waits/readback and maintain resident work state. | Neither a native search loop nor graph execution is implemented in current path. Earlier concurrent-stream experiments were tested separately. | First measure host gaps on current winner, then compare same canonical work including cancellation latency and complete candidate/guard readbacks. Never credit unfinished or stale batches. Treat as overhead reduction, not cheaper matrix math. |
| 4 | Exact structured-noise algebra | Investigate whether compact noise permits fewer operations while reproducing every prefix checkpoint. | Feasibility research only. | Prove equivalence under signed-byte wrapping, cumulative int32 arithmetic, all 256 K128 checkpoints, nonlinear XOR/rotate transcript folding, tail changes and fresh nonce/proof binding. Reject simple factorizations that match only final matrix products. |

## V080 recorded outcome

Approximate values transcribed from the completion screenshot; complete reports remain on the rig.

| Mode | Offline median tiles/s | GPU-board W | Tiles/J | Decision |
| --- | ---: | ---: | ---: | --- |
| pair-direct | 2,350,203 | 84.19 | 27,747.68 | Retained |
| pair-step2 | 2,165,867 | 76.49 | 28,169.60 | Slower; highest observed tiles/J, throughput tradeoff |
| pair-step8 | 2,391,880 | 85.07 | 27,945.12 | +1.77% speed; below promotion margin |

Live pair-direct: 673,054,720 completed tiles, 77 full nonces, approximately 300.138 s actual elapsed and 2,242,481 tiles/s across the whole attempt. Twenty status reports acknowledged; zero shares sent or accepted. Worker joined and WildRig restored, exit 0. Pool share acceptance remains unproven. User separately reported 11.9 TH/s on the pool display; this is a reported display observation, not independently measured accepted-share throughput or a directly comparable offline tile rate.

## Already explored

- Compiler-forced three/four-block residency: spills and large speed losses (V077).
- 512-thread / 64-tile blocks: slower; 32K/64K dispatches only small speed gains and worse measured efficiency (V078).
- Eight-tile warp packing: both simultaneous and serial variants lost (V069).
- Shared-A staging lost against matched paired direct control, although paired layout itself won (V079).
- Shared-B row reuse and multiple B stage depths, consumer unrolling, separate producer pipeline, bounded materialised B panels: tested in V070/V074–V076/V080.
- Two concurrent streams were tested in V041–V044; this does not establish the outcome of a new graph/native loop on the current kernel.
- Early 2x8 cooperative/materialised kernel lost in V033–V035. Larger cooperative designs must address that result, not repeat it under a new name.
- Cached nonce commitment frontier, per-job B tables and resident geometry are already implemented.

## Execution rules

One architectural variable per experiment, current measured winner as control, equal canonical work sets, automatic power monitoring. A throughput loser with better tiles/J remains an explicit efficiency tradeoff, not the default speed winner. Preserve exact target/proof semantics and report status acknowledgements separately from real accepted shares. No unmeasured speedup forecast is a result.
