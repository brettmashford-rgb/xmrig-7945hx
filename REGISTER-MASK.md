# Register-held addresses plus loop mask reduction

Combines the guarded register-pointers experiment with four VPTERNLOGQ instructions replacing four ANDPD plus four ORPD instructions in its loop-load template. Immediate 0xea computes (converted value AND xmm13) OR xmm14. Existing masks, memory accesses and iteration ordering are unchanged.

Only the existing AVX-512F/VL, full-memory, non-XOP, non-V2 pointer path changes. Other paths retain the original stack and mask templates. Generated template sizes determine branch offsets.

This removes four loop instructions per iteration (65,536 per hash) relative to register-pointers. Register-held pointers still replace two stack saves and two reloads per iteration. Instruction savings do not establish throughput or power improvement.

Validation: full local production miner build passed. 512 generated VM programs at 32 iterations each matched the forced original fallback in every register and every byte of their 2 MiB scratchpads. Optimized selection and fallback restoration checks passed. Full patch replay, builder shell syntax and runner Python compilation passed.

Run on Alpine with the pool miner stopped:

    python3 run-experiment.py register-mask

Uses separate source/output trees and does not install or restart the pool miner. The runner checks the 1M checksum 898B6E0431C28A6B. Target performance and wall power must be measured.

Production local 250K rx/0 benchmark checksum 7D6054757BB08A63 passed. Local timing is not a target Ryzen speed or power prediction.
