# Register-mask plus rounding-mode cache-store scheduling

Starts from register-mask, retaining register-held scratchpad addresses and ternary loop masks. Adds the earlier round-store scheduling experiment. VAES-256 and dataset-prefetch experiments are excluded.

In both AMD CFROUND emitters, moves the cached-mode write to [rsp+32] before LDMXCSR. The equality check still skips the complete update when the cached mode matches. All mask operations, MXCSR table addresses, the post-load jump and total 19-byte emitted update length are unchanged. Therefore eliminated-update NOP spans, generated branch displacements and V2 skip lengths remain valid. Non-AMD CFROUND sequences are unchanged.

This changes scheduling rather than removing instructions or suppressing rounding updates. The hypothesis is that placing the independent cache store ahead of LDMXCSR may help the current combination. Target performance and wall power are unproven.

The builder uses separate source/output trees, pinned upstream source, generic build settings and AES prefetch distance 7168. It refuses unexpected source changes. The runner never installs a miner or changes startup.

With the pool miner stopped, build and test:

    python3 run-experiment.py register-mask-round

The target 1M benchmark must match checksum 898B6E0431C28A6B.

Local validation: full production build passed. 512 generated VM programs at 32 iterations matched the forced original path in registers, complete 2 MiB scratchpad and final MXCSR. Candidate pointer-template selection and light/non-full/V2 fallback restoration passed. Both AMD CFROUND emitters retain the same 19-byte update size. Patch replay, shell syntax and runner compilation passed. Test instrumentation is excluded from production.

Production local 250K rx/0 benchmark checksum 7D6054757BB08A63 passed. Separate-host timing does not predict target Ryzen speed or wall power.
