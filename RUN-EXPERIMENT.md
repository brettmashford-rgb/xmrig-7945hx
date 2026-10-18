# Target-machine experiment runner

From the repository directory on the Alpine miner:

```sh
python3 run-experiment.py
```

The default is the reviewed `fp-convert` experiment. The script runs its existing
builder, then a 1M `rx/0` benchmark. It checks the expected checksum
`898B6E0431C28A6B` and interrupts its own benchmark after completion, avoiding the
normal wait for Ctrl+C. It does not install a binary, change startup, restart
mining, upload results, or modify BIOS settings.

If a pool miner is active, stop that miner first. For the existing tmux setup:

```sh
tmux send-keys -t xmrig C-c
```

After testing, resume the existing pool miner once with:

```sh
sh /etc/local.d/*.start
```

## Results

Results are saved in a fresh directory under `/media/usb/xmrig-test-results` if
that mount is writable; otherwise under `test-results` in the repository.
The output prints the exact directory. Files are `summary.txt`, `result.json`,
`benchmark.log`, and (when building) `build.log`. Results are local; the runner
never commits or uploads them. Save RAM-backed results before rebooting.

Supply wall power only if measured during this test, for example:

```sh
python3 run-experiment.py --skip-build --watts 96
```

`--skip-build` reuses the existing experiment binary. Wall power cannot be read
from an external power meter by this script. Optional choices are `fp-convert`,
`round-store`, and `round-nop`; it runs only the selected experiment and does not
repeat the baseline. Correctness passing does not establish a speed improvement.

Requires Python 3 (already used by the JIT profiling tools). Build dependencies
are managed by the existing Alpine builders. The build limit is one hour and the
benchmark limit is 15 minutes. Ctrl+C stops only the runner's child command group.
