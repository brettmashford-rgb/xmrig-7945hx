# Single-instruction FDIV divisor masking

Isolated experiment on register-mask. Replaces the two AND/OR instructions preparing FDIV_M divisors with one 128-bit VPTERNLOGQ instruction, truth table 0xEA: (input & mask) | exponent. Division itself and instruction ordering are unchanged.

Runtime feature gating requires AVX-512F and AVX-512VL. Existing XOP and unsupported CPU implementations remain available. No scratchpad VAES or program-generation VAES changes are included.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py fdiv-ternary
```

Builds separately without installing or changing startup. The runner checks the full 1M checksum. Measure target hashrate and wall power; reducing instruction count does not establish a performance gain.
