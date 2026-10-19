# Early floating memory operands on register-mask

Starts from register-mask. Adds early operand loading/conversion for FADD_M and FSUB_M; arithmetic stays in its original VM position. No early dataset hints, rounding-store reorder or VAES-256 are included.

A planning pass classifies the 256-instruction VM program with the pinned BytecodeMachine. It schedules at most one live operand in otherwise unused XMM18 and requires at least three intervening VM instructions. A load cannot cross an address-register writer (including either side of a swap), ISTORE, CFROUND, CBRANCH or branch target. Every backward branch target is a block boundary. Thus a branch cannot jump past a required preload and stores cannot change the loaded bytes between preload and arithmetic. Conversion from signed 32-bit integers to double is exact.

Native emission uses EVEX VCVTDQ2PD XMM18,[RSI+RAX], and VADDPD/VSUBPD with the original destination as the first source. Original arithmetic order and exception behavior are retained. Register-pointer AVX-512F/VL CPU/OS guards also gate this scheduling path; light/non-full/XOP/V2 and non-256-instruction programs retain their existing fallback. XMM16/17 still hold the two scratchpad addresses. Original CFROUND elimination and branch offsets are generated while emitting the final schedule, rather than patched after relocation.

The new plan requires a separate bytecode classification pass, and native instructions are slightly longer. It could overlap loads with useful work, but can also increase queue pressure, code size or JIT overhead. No target speed or power gain is established.

Local validation: full production build passed. 512 random generated VM programs executed for 32 iterations each matched the forced original path in all registers, all 2 MiB scratchpad bytes and final MXCSR. The test exercised 1906 native operand hoists and verified register-pointer selection and light/non-full/V2 fallback restoration. Test instrumentation is excluded from production. A prior interpreter scheduling prototype separately passed 128 cases. Full canonical patch replay passed.

Alpine command, with the pool miner stopped:

    python3 run-experiment.py operand-hoist

The separate source/output builder uses pinned upstream source, generic settings and AES prefetch distance 7168. The runner checks the 1M rx/0 checksum 898B6E0431C28A6B. It never installs a miner or changes startup.

Production local 250K rx/0 checksum 7D6054757BB08A63 passed. This run reported 2015.9 H/s on the separate Intel host; no matched control was run, so it establishes correctness rather than a speed gain. Initial random native tests used zero A-register constants; an additional random native test uses nonzero finite A-register constants.

The additional 512 native cases with nonzero finite A-register constants also passed, exercising 1882 further hoists: 1024 cases and 3788 native hoists across both suites.
