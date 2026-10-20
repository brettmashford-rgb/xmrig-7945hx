# JIT code placement shifted by 32 bytes

Experiment on body-align32. Shift each allocated JIT code base by 32 bytes while retaining the existing inter-thread code-offset stride and 32-byte VM body alignment. This changes the code position within 64-byte cache lines without adding executed instructions or padding relative to body-align32. Existing allocation headroom covers the additional offset.

Native validation: 512 generated VM programs produced byte-identical code relative to body-align32 and matched all registers, complete 2 MiB scratchpads and MXCSR at 32 iterations each. This establishes correctness for those cases, not a speed or power gain.

No branch-pair padding, swap-moves, address compaction, floating-swap, rounding-cache, FDIV or VAES changes are included.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py jit-phase32
```

Builds separately without installing or changing startup. The runner validates the full 1M checksum.
