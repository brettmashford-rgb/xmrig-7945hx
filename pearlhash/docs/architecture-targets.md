# PearlHash architecture targets

Updated 2026-11-12 from the rig's V080–V083 completion screenshots. This is the ordered backlog for larger changes; completion means measured rig evidence, not just implemented code.

| Order | Target | Mechanism | Status | Evidence required |
| --- | --- | --- | --- | --- |
| 1 | Compute-layout redesign | Rebalance row/column ownership and input reuse across warps while controlling accumulator registers. | V081 completed. Pair-direct retained: 2,326,001 tiles/s, 84.20 W, 27,737 tiles/J. The 8x4 layout lost 9.9% throughput; 4x8 lost 29.0%; both were less efficient. All had 96 registers/thread, zero local bytes and two active blocks/SM. Broader cooperative redesign remains open. | Identical transcripts and canonical coverage, independent CPU/V3 proof checks, equal-work speed, native resources and full-nonce board energy. Retain control unless median elapsed improves >3%. |
| 2 | Multi-nonce B reconstruction reuse | Share reconstructed B fragments during scanning across distinct A/nonces for the same job, beyond existing per-job B tables. | V082 completed. Shared B improved the matched two-nonce block by 4.52%, but still lost 3.49% throughput and approximately 0.27% efficiency versus pair-direct. Pair-direct retained at 2,374,659 tiles/s. Other multi-nonce layouts remain untested. | Distinct nonce bindings, per-nonce transcripts/hits, exact coverage, cancellation and ownership, memory footprint and total unique work/s including setup. B already has substantial reuse across rows; do not assume another factor-of-two saving. |
| 3 | Native dispatch / CUDA Graphs | Reduce Python/driver work, batch waits/readback and maintain resident work state. | V083 completed. Native direct +0.37%, graph +0.22%; pair-direct retained. Scanner event interval covered about 94% of instrumented wall time, suggesting limited dispatch-only headroom. Full native worker/persistent-loop designs remain untested. | Compare the same canonical work, include cancellation and complete readbacks, and distinguish overlapping GPU events from host clocks. |
| 4 | Exact structured-noise algebra | Reformulate checkpoint-local products through the B basis, retaining exact high-byte and constant corrections. | V084 built; GPU results pending. Exact scalar identity checked at all 256 checkpoints. Same six MMA instructions per K32 step; moves B reconstruction out of the hot loop and adds bounded sparse correction/preparation. | Exact cumulative int32 products and folds, nonce-tail correctness, fresh proof bindings, all guards, whole-nonce time and upfront job amortization. A final-product-only identity is insufficient. |

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
