# VAES-256 fused scratchpad hash/fill experiment

Based on register-mask: keeps register-held scratchpad addresses and ternary loop masks, and changes only the hardware fused AES hash/fill path beyond that baseline.

Pairs even and odd 128-bit lanes in two 256-bit vectors. Each 64-byte scratchpad chunk uses four VAES operations instead of eight scalar-width AES operations. Input and output lane permutations preserve the existing layout, AES directions, keys and finalization. Prefetch distance remains configurable, with the target builder fixed at 7168 bytes. This does not remove a scratchpad pass; the existing worker already fuses hash and fill.

GNU x86-64 builds isolate AVX2/VAES intrinsics with a function target attribute. Runtime compiler feature detection checks AVX2 and VAES including OS vector support. Only hardware AES selects it; software AES and unsupported machines keep their previous paths. Existing Zen 5 VAES-512 dispatch takes precedence. Unaligned vector accesses preserve compatibility with existing 16-byte-aligned buffers. VZEROUPPER precedes return to the regular JIT path.

Validation: full production miner build passed. 64 integrated cases compared against the forced original hardware path across 7168-byte, 8 KiB, 64 KiB and 2 MiB buffers, eight random seeds each, with both 64-byte and 16-byte-offset alignment. Final hash, fill state and the entire scratchpad matched, and a test counter verified candidate dispatch. Test instrumentation is excluded from production. Full canonical patch replay, builder shell syntax and runner Python compilation passed.

Build and test on Alpine with the pool miner stopped:

    python3 run-experiment.py vaes256

Separate source and output directories preserve the other experiments. No binary is installed and startup is unchanged. Target runner checks the 1M checksum 898B6E0431C28A6B.

The change trades fewer AES operations for lane permutations and a different loop schedule. It has not established an improvement in target throughput or wall power. Compare against register-mask at unchanged rig settings.
