# Structural opportunities after validated v059

The current baseline is recorded in development-baseline.json. v059's offline
proof/correctness gates passed, and stride six measured 888491.13 tiles/s
against v057 855774.17 (+3.82%). v054 is still the last live-validated worker.
No new kernel or live run is introduced by this audit. This document records
source-derived opportunities, not measured gains for unbuilt implementations.

## 1. Reuse B reconstruction across row tiles

The current kernel gives each warp one 10x16 canonical tile. It reconstructs
four B fragments at each of 1024 K steps for that tile. For a fixed column
axis, those B values are identical across all 512 row axes. Current row-major
scheduling visits all 16384 column axes before moving to the next row axis,
so that reusable computation is performed again for every row tile.

First prototype: one warp handles two row tiles sharing the column axis,
reconstructs/transposes B once, and feeds two independent A/accumulator sets.
This can halve B reconstruction work for the pair without materializing an
8-GiB B matrix. It keeps both transcripts and candidate identities distinct.
This is a work-count opportunity; extra accumulators/registers and reduced
occupancy may offset savings. No throughput estimate is asserted.

It requires an explicit traversal mapping between physical work order and
canonical row-major tile ID. That mapping must be a tested bijection across
all 8388608 tiles. Candidate CPU checking/proof construction must receive the
canonical ID, and overflow/stale cancellation must preserve exact coverage.
A new scheduler must not silently reinterpret the existing FastPlan cursor.
Controls must search the same canonical tile set, not merely the same count.

## 2. Pack real rows into tensor operations

The m16n8k32 primitive used twice per tile computes 16x16 outputs for a 10x16
query. Six of sixteen row positions are padding: 37.5% of these matrix-row
positions are unused. Eight canonical row tiles contain 80 actual rows.
They could occupy five full 16-row slabs instead of eight padded slabs,
reducing the group's matrix calls per K step from sixteen to ten.

This is a later extension of shared-B processing, not a 37.5% whole-miner
speed promise. It needs separate transcript reductions at each tile's 10-row
boundary, including boundaries crossing an MMA slab. Accumulator/register
pressure, shuffle/reduction costs and any CTA synchronization could erase
savings. Prototype two-row-tile B reuse first; extend to packed rows only
if its resource/timing results justify the extra complexity.

## 3. Cache the A commitment frontier across nonces

prepare_nonce in pool/search.py calls constant_opening for the full A matrix
on every nonce. A is filled with 64; only its last sixteen bytes depend on
the worker/miner nonce. The production tree has 163872 1024-byte leaves.
blake3_cpu.cpp recursively rebuilds every leaf and all 163871 internal nodes.

A verified per-job frontier can retain unchanged subtree chaining values.
Updating the final leaf requires one chunk hash and seven parent hashes for
this particular non-power-of-two production shape. The tree has eighteen
levels, with unchanged right-edge nodes promoted at the other levels.
Existing native chunk_value/parents primitives already expose the required
keyed hashing, including the distinct final-root flag.

Cache identity must include job key, dimensions, fill and tree layout. The
changed tail, resulting root and derived noise seeds must remain bound to
the current nonce/generation. If the existing prepare_nonce opening contract
is retained, its row-zero opening must also be reconstructed and verified;
supplying a cached root alone is insufficient. Candidate proof construction
continues to independently reconstruct/verify fresh openings.

This is a large reduction in commitment work with a smaller overall ceiling:
in v054, nonce preparation took 17.312 seconds, search 267.774, cache 10.689
and base 1.722. Eliminating ALL nonce-preparation time would improve throughput
by at most about 6.2% for that measured stage mix. A real implementation has
initial per-job cache construction and remaining nonce work. Faster scans
may make preparation a larger fraction later. It could also reduce blocking
native work during stale-job shutdown and CPU competition with XMRig.

## 4. Retain immutable B noise tables across nonces

dense_noise_seeds in reference/seeds.py derives b_seed only from job_key and
the dimension-bound B root. The changing A root is used only for a_seed.
Thus B uniform bytes and permutation remain identical across nonces of the
same job/profile. VirtualTables currently allocates and regenerates both
sides for every new nonce, and ResidentBackend.close releases both sides.
The B uniform table alone is n*rank=33554432 bytes (32 MiB), plus a 128-KiB
permutation and guards/key. Sharing a verified per-job B table across nonce
backends would avoid that repeated generation without changing scanner math.

The existing live worker already retains its scanner context across nonces,
so the ownership extension is localized compared with a new tile scheduler.
Borrowed/shared B buffers need explicit lifetime and exact job/seed/profile
binding, must retain every guard check, and must be released on job/context
close. Per-nonce A tables/tail remain distinct. Benchmark fresh-nonce setup
and whole-work elapsed, not just search tiles/s: this changes preparation,
not the steady-state scan kernel. Last live cache time was 10.689 seconds,
which includes A work too; only its B-generation component is removable.

## 5. Chunked materialized B: larger redesign, uncertain payoff

The full noised B matrix is 262144x32768 bytes = 8 GiB, before A/noise/guards
or driver memory, so it cannot be allocated on this 8-GB rig. A bounded B
chunk could be materialized and reused across row tiles instead. But changing
traversal can destroy current A locality, and materialized B introduces more
memory traffic. Current row-major order reuses each roughly 320-KiB A tile
across 16384 column axes. Any chunk design must account for both A and B
reuse, measure actual traffic/timing and report materialization setup costs.
Do not infer a win from removed arithmetic alone (v058 already demonstrated
why that inference is insufficient).

## Suggested sequence

Start with two-row-tile B reuse as the largest plausible GPU work reduction.
Test exact transcripts, canonical mapping, queues/overflow, all guards,
independent CPU samples and a fresh V3 proof before timing against v059.
Report registers/shared/local resources and equal canonical work sets.
Keep the Merkle-frontier cache and per-job B table ownership as separate
experiments so their setup effect can be measured without mixing them into
a new GPU scheduler. Keep the same rig clocks,
CPU miner, pools and permanent service definitions. No pool acceptance claim
follows from any offline improvement.
