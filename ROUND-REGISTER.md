# Register-held rounding cache

Isolated experiment on register-mask. CFROUND caches the last masked rounding selector in XMM18 instead of a stack slot. Each CFROUND reads the cached value through ECX and updates XMM18 when loading a different MXCSR. The MXCSR table and actual LDMXCSR operation remain unchanged.

Enabled for GNU x86-64 Linux, AMD full-memory flags, AVX-512F/VL, and the original non-XOP/non-V2 route. Original initialization and instruction sequences are restored for other modes. No swap-moves, FDIV or VAES changes are included.

This removes stack accesses but adds register transfers and code bytes. Target speed or power improvement is not established.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py round-register
```

Builds separately without installing or changing startup. The runner validates the full 1M checksum.
