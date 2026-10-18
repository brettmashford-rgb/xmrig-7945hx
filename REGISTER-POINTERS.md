# Register-held scratchpad addresses experiment

Standalone change on the selected generic RCP/no-donation baseline with AES prefetch distance 7168. It does not include mask reduction, dead-store elimination, or dataset hint experiments.

Normal full-memory rx/0 can hold its two per-iteration scratchpad addresses in XMM16/XMM17 instead of saving and loading them at `[rsp+16]` and `[rsp+24]`. The four stack accesses become four EVEX VMOVQ register transfers. All actual scratchpad writes, reads, arithmetic and iteration ordering are retained.

Selection requires GNU x86-64, AVX-512F and AVX-512VL as reported by the compiler's CPU/OS feature detection, full-memory flags, no XOP, and no V2 AES/prefetch tweaks. Other paths retain the original templates. Template sizes and generated branch displacements are calculated from the selected code. No new JIT instance fields or VM register-state layout changes are introduced.

The stack path is restored if the compiler instance is subsequently used for light or V2 mode. New templates are appended outside the existing assembly symbol ranges. XMM16/XMM17 are volatile in the relevant ABI and otherwise unused by the selected JIT helpers. No upper YMM/ZMM lanes are used by the new instructions.

Local validation: a complete local miner build with TLS and benchmarking enabled. A separate test build checked 512 random generated VM programs for 32 iterations each against the forced original stack path; every register file and complete 2 MiB scratchpad matched. The test verifies that the optimized template is actually selected and that light/non-full/V2 modes restore the stack template. Earlier standalone kernel checks also passed 100 cases. These are correctness checks on a separate Intel host, not target speed or power measurements.

Build on the existing Alpine project: `sh build-jit-rcp-register-pointers.sh`.

Build and checksum-test: `python3 run-experiment.py register-pointers`.

The builder uses separate source/output trees. The runner does not install a binary or change startup. Full target Alpine compilation, throughput and wall power remain to be measured. Instruction count is unchanged: performance depends on the register-transfer cost versus the removed stack operations.

Production local 250K benchmark checksum: 7D6054757BB08A63 (passed). The target runner checks 898B6E0431C28A6B for its 1M run.
