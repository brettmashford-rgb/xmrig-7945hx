# Three-move integer swaps

Isolated experiment on register-mask. For ISWAP_R with different source and destination registers, replace register XCHG with three 64-bit moves through the existing RAX temporary. Equal-register swaps remain empty. VM register values and condition flags are preserved.

This adds instructions and code bytes; the hypothesis is that register renaming may make the moves cheaper to execute. A gain is not established. No FDIV ternary or VAES experiment changes are included.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py swap-moves
```

Builds separately without installing or changing startup. The runner checks the full 1M checksum. Compare sustained target hashrate and wall power.
