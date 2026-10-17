# Experimental removal of unused reciprocal setup

This candidate starts from the working immediate-RCP rewrite with complete donation removal. It includes neither swap-moves nor compact-add.

The old reciprocal strategy initialized 16 stack constants using sixteen MOV-immediate/PUSH pairs followed by ADD RSP,128. The immediate-RCP emitter reads none of those stack slots. This patch removes those 33 setup instructions from the shared assembly include. The include's exported label remains so the existing eMask patch location is unchanged. Stack allocation and epilogue layout remain unchanged because the removed pushes and their matching stack adjustment have zero net stack effect. The loop-load code overwrites RCX before using it, so the removed setup's RCX value is unnecessary.

This is setup once per VM program invocation, not work inside each iteration of the VM loop. Expected impact may be small; this is not a proven performance or power improvement. The assembly template becomes smaller, so code alignment and placement also change.

## Build on Alpine

```sh
git pull --ff-only
sh build-jit-rcp-setup.sh
```

Output: `.work/build-7168-jit-rcp-setup/xmrig`. Source: `.work/xmrig-jit-rcp-setup`. Generic compiler flags, prefetch distance 7168 and no LTO remain. The script neither starts nor stops miners and makes no installation or startup changes. Unknown edits in its source tree cause refusal.

Stop the pool miner before testing:

```sh
.work/build-7168-jit-rcp-setup/xmrig --bench=1M --algo=rx/0
```

Expected checksum: `898B6E0431C28A6B`. Record final hashrate and wall power. Keep the installed RCP binary until an improvement is demonstrated.

## Verification

The changed GNU assembly template compiles with the existing full Linux CPU miner's Release settings and links into the complete miner with TLS, HTTP/API and benchmark support. Disassembly confirms the setup label now jumps directly to the loop, with no reciprocal MOV/PUSH sequence. The full miner passes the offline 250K rx/0 checksum `7D6054757BB08A63`. The combined patch is replayed against the pinned clean upstream revision. The Alpine target build and performance remain to be tested; Windows/MASM and software-AES operation have not been tested locally.
