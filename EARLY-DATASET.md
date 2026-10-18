# Earlier dataset prefetch experiment

This isolated experiment starts from the selected RCP/no-donation build with
AES prefetch distance 7168. It does not combine the rejected rounding or AVX
conversion experiments.

The normal rx/0 dataset reader already prefetches the next iteration's dataset
line. This change adds an earlier hint after the last branch and last writer of
either address-input register, when at least 64 bytes of VM code remain. The
existing hint stays in place. The hypothesis is that independent trailing VM
work can overlap more of the memory wait. Added instructions and hints can also
hurt performance; a single-DIMM gain is not established by correctness tests.

The address is `(high32(rbp) ^ low32(readReg2) ^ low32(readReg3)) & dataset_mask`,
matching the original reader after its RBP rotation. RAX and RDX are temporary
registers; no VM register or RBP is modified. CBRANCH marks all register-use
positions, so the insertion point is after all VM branches. Moving the tail
therefore leaves existing branch displacements valid. CFROUND's local jumps
move together with their targets. Loop-tail branches are generated afterward.
Light mode and RandomX v2 prefetch behavior are unchanged.

Build alone:

```sh
sh build-jit-rcp-early-dataset.sh
```

Build, test the 1M checksum and save results (stop the pool miner first):

```sh
python3 run-experiment.py early-dataset
```

The generic runner default remains fp-convert; select early-dataset explicitly.
The experiment is not installed automatically. Results remain local.
