# 32-byte VM body alignment

Isolated experiment on register-mask. After the fixed scratchpad-load template, emit multi-byte NOP padding to align the generated VM instruction body to an absolute 32-byte boundary. The outer-loop target remains unchanged. Padding is enabled only when the existing register-pointer template is selected; other paths remain unpadded.

Arithmetic and memory operations are unchanged. Register usage positions and branch displacements are generated after padding. The added NOPs execute on each outer iteration, so any fetch/decode benefit must outweigh their cost. No speed or power gain is established.

No swap-moves, floating-swap, rounding-cache, FDIV or VAES experiments are included.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py body-align32
```

Builds separately without installing or changing startup. The runner validates the full 1M checksum.
