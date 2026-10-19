# VAES-256 program generation

Isolated experiment on register-mask. Pairs the four AES states into two 256-bit vectors in fillAes4Rx4, preserving the unmasked entropy and masked instruction bytes. This differs from the earlier scratchpad hash/fill VAES experiment.

Runtime dispatch requires AVX2 and VAES; other CPUs and software AES retain the existing implementation. Builds separately and does not install or change startup.

With the pool miner stopped:

```sh
cd /root/xmrig-7945hx && git pull --ff-only && python3 run-experiment.py program-vaes256
```

The runner verifies the full 1M RandomX checksum. Compare wall power and sustained hashrate on the target; component timings on another CPU do not establish a mining gain.
