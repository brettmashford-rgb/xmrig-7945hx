# Compact early dataset address preparation

This experiment starts from early-dataset and keeps both NTA hints. It does not
include T0 hints or the early-once late-hint removal.

On BMI2-capable CPUs, calculate the early address with:

```
rorx rdx, rbp, 32
xor edx, readReg2d
xor edx, readReg3d
and edx, dataset_mask
prefetchnta [rdi+rdx]
```

The existing form is seven instructions and 25 bytes, including the hint. This
form is five instructions and 22 bytes and avoids using RAX as a temporary.
RBP and the VM registers are unchanged. The original 25-byte sequence remains
as fallback without BMI2. Hint eligibility is unchanged: the insertion is after
all address-input writers and VM branches, with at least 64 trailing code bytes.

This tests instruction overhead; it does not provide additional RAM bandwidth.
A native checksum pass does not establish target-machine performance.

Stop the pool miner before running:

```sh
python3 run-experiment.py early-compact
```

The runner builds and tests separately without installing or restarting mining.
The runner default is unchanged, so use the explicit experiment name.
