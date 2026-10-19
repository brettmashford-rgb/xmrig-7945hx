# Body alignment plus integer swap moves

Combines the isolated body-align32 and swap-moves changes on register-mask. Aligns the generated VM instruction body to 32 bytes using multi-byte NOP padding, and replaces nontrivial ISWAP_R register exchanges with three 64-bit moves through the existing RAX temporary.

No floating-swap, rounding-cache, FDIV or VAES experiments are included. Benefits from separate changes need not add together; target hashrate and wall power must be measured.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py align-swap
```

Builds separately without installing or changing startup. The runner validates the full 1M checksum; --skip-build --bench 10M supports a longer follow-up.
