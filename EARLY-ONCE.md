# Early dataset hint without the late duplicate

This follows the earlier-dataset experiment. When that pass emits an early hint,
replace the later `mov edx,ebp; and edx,mask; prefetchnta [rdi+rdx]` sequence with
8-byte and 4-byte NOPs. Code layout and all memory loads stay unchanged.

RDX from this late sequence is not used by the remaining dataset XOR loads;
the scratchpad-prefetch sequence redefines RDX before using it. RBP and RAX
updates remain intact. Programs without an early hint retain the original late
sequence. The replacement requires an exact 12-byte match inside the copied
rx/0 reader; if absent it conservatively keeps the late hint. Light mode and
RandomX v2's reader are unchanged.

The purpose is to test whether an early hint can replace the later hint and its
address calculation. Repeated hints do not necessarily cause duplicate DRAM
reads. No performance gain is established without target-machine measurements.

Run after stopping the pool miner:

```sh
python3 run-experiment.py early-once
```

The runner builds into a separate source/output tree and checks the 1M rx/0
checksum. It does not install or restart mining. The earlier-dataset build is
kept separately for comparison. The runner's default remains fp-convert, so use
the explicit experiment name above.
