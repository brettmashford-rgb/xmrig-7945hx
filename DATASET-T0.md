# Dataset T0 cache-hint experiment

This is based on the first early-dataset experiment, retaining both the optional
early hint and the original late hint. It changes both rx/0 dataset prefetch
sites from PREFETCHNTA to PREFETCHT0. The code size, addresses, loads, arithmetic,
and hint timing stay the same. The later duplicate is retained, so this tests
cache-hint policy separately from the early-once experiment.

T0 requests ordinary temporal caching. It may help data availability or may
increase competition with scratchpad lines. Actual cache placement is
processor-dependent; the hint does not guarantee a memory transaction or a
particular performance gain. Measure on the single-DIMM target.

Light mode and the separate RandomX v2 dataset reader are unchanged. The normal
rx/0 reader uses T0 even in programs whose tails are too short for an early hint.

Stop the pool miner before running:

```sh
python3 run-experiment.py dataset-t0
```

The runner builds into separate source/output trees and checks the 1M rx/0
checksum. No binary is installed, no pool is restarted, and results remain local.
