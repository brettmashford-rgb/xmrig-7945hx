# Operand hoisting with a classification-only planner

Retains the operand-hoist native scheduling and single-XMM18 lifetime rules on register-mask, but removes its full BytecodeMachine compilation pass. A lightweight opcode classification table uses the current configuration frequencies. It records integer writes, swaps, branch targets and store/rounding barriers without calculating reciprocals or constructing interpreter register pointers. Zero/power-of-two IMUL_RCP and same-register swaps are treated as NOPs for dependency analysis. No native instruction scheduling policy is intentionally changed.

Motivation: the target operand-hoist experiment passed checksum but regressed in speed. This does not establish the cause. A separate-host matched synthetic component diagnostic showed additional planning cost equivalent to roughly 2-4% of execution after amortization over 2048 iterations. Native runtime comparisons varied. The diagnostic alternates execution order and prefaults its synthetic dataset mapping; it does not reproduce target cache/DRAM behavior. No Ryzen speed or power prediction follows.

Local correctness: 128 paired generated-program cases at 512 iterations each passed in each of three diagnostic trials. A further 512 cases at 32 iterations with nonzero finite A-register constants passed, exercising 1882 hoists. Every register file, complete 2 MiB scratchpad and final MXCSR matched register-mask/original reference as appropriate. CPU guards and light/non-full/V2 restoration checks passed. Test-only mode 2 allows a register-mask comparison and is excluded from production. Canonical patch replay, shell syntax and runner compilation passed.

The changed production JIT translation unit was compiled and the full miner relinked using the existing CMake compile/link commands and unchanged existing objects. The local CMake driver crashed before invoking the compiler; direct compiler/link commands completed instead. Target Alpine compilation remains untested.

Prepared target command, after publication:

    python3 run-experiment.py operand-lean

Separate source/output trees. No binary installation or startup changes. The target runner verifies 1M checksum 898B6E0431C28A6B. Register-mask remains the preferred target candidate. The lean planner is not a confirmed improvement.

Production local 250K rx/0 checksum 7D6054757BB08A63 passed. Separate-host full-run timing did not establish a speed improvement; an unmatched earlier operand-hoist run is not a valid control.

Publication uses operand-lean-only.patch, a JIT-only delta on the existing rcp-register-mask.patch. The builder constructs and compares the expected combined source in a temporary local clone. This reproduces the checksum-tested source exactly without repeating baseline donation deletions in the new patch.
