# Conditional branch-pair alignment

Experiment on body-align32, which already includes register-mask. On the AMD route without the existing Intel Jcc erratum workaround, insert multi-byte NOPs before CBRANCH when its TEST/Jcc pair would cross a 32-byte boundary. The ADD still executes before TEST, and branch displacements are calculated after padding.

The existing Intel erratum path is unchanged. No swap-moves, floating-swap, rounding-cache, FDIV or VAES experiments are included.

Native validation compared 512 generated programs at 32 iterations each against body-align32: all register files, complete 2 MiB scratchpads and MXCSR matched. The sample added 16,323 bytes at 3,435 branch sites across 512 programs. Padding executes and enlarges the generated code; no target gain is established.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py branch-align32
```

Builds separately without installing or changing startup. The runner validates the full 1M checksum.
