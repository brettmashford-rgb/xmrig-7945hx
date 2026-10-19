# PSHUFD floating register swaps

Isolated experiment on register-mask. FSWAP_R uses PSHUFD with mask 0x4E instead of SHUFPD with mask 1. Both exchange the two 64-bit halves bit-for-bit and leave MXCSR unchanged. Each remains one five-byte instruction.

Any benefit depends on target execution behavior; instruction count and code size do not decrease. No integer swap-moves, rounding-register, FDIV or VAES changes are included.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py fswap-shuffle
```

Builds separately without installing or changing startup. The runner validates the full 1M checksum.
