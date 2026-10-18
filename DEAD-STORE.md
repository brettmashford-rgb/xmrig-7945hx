# Conservative overwritten-store experiment

This experiment changes only JIT compilation. It retains every address computation and instruction offset, replacing an earlier ISTORE memory write with a four-byte NOP only when a later ISTORE has the same address register version, effective address mask, and immediate modulo scratchpad size. Immediate normalization includes the low three bits, preserving carry into the aligned address.

Any scratchpad read, branch, or unknown handler clears pending candidates. Address-register writes invalidate matches through the existing registerUsage version. No store is removed across a VM program boundary. No non-temporal stores or new prefetches are introduced.

Build: `sh build-jit-rcp-dead-store.sh`

Test: `python3 run-experiment.py dead-store`

The builder and runner do not install the binary or change startup.

Local correctness validation: 10 targeted cases plus 1,024 random programs, each comparing all 256 bytes of register state and both full 2 MiB scratchpads after 16 VM iterations. All matched with 517 deliberately exercised dead-store removals. The cases include intervening reads, branches, address-register writes, other-register writes, differing masks, immediate wraparound, differing low immediate bits, different base registers, and repeated overwrites. A test-only compile flag enables the reference emission path and counters; production builds exclude them.

Opportunity limitation: zero removals occurred in the 512 unmodified random programs in that test. Correctness is established for the tested cases, but no meaningful performance gain is claimed. Full Alpine builds and target throughput remain to be tested.

Production local 250K rx/0 checksum: 7D6054757BB08A63 (passed). This was an eight-thread separate-host correctness run, not a target speed comparison.
