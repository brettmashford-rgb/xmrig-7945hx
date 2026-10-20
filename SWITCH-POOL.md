# Switch existing Alpine miners to SupportXMR

`switch-pool.py` updates the pool command in an existing `/etc/local.d/*.start` script. It retains the existing miner executable, copy/chmod commands, tmux session name, and non-pool options such as threads and CPU affinity. It does not deploy the 7945HX binary to other CPU models.

Run as root on each rig with Python 3.9 or newer:

```sh
python3 switch-pool.py --wallet YOUR_MONERO_ADDRESS
```

The script extracts a worker name from the suffix of the existing NiceHash username (`address.worker`). If none is recognised, it prompts for a name. Use `--worker NAME` to override it; use distinct names for separate rigs if separate dashboard entries are wanted. The wallet is an argument or an interactive input, not embedded in this repository. Format checking does not verify ownership or the address checksum.

The new connection is `pool.supportxmr.com:443`, TLS, rx/0, using the wallet as username and worker name as password. NiceHash-specific settings and previous pool options are removed. Existing CPU tuning is retained.

Before modifying startup settings, the script requires a mounted `/media/usb`, makes a timestamped startup-script backup there, and gracefully stops the matching tmux miner. It refuses to change startup settings if another miner remains running or the old session remains. It writes the updated script, runs `lbu commit`, syncs, starts the miner, and captures recent terminal output. Confirm new pool jobs and accepted shares afterward. It attempts to restore the original script and restart the previous miner if saving fails.

Only one simple, quoted, single-line `tmux new-session -d -s NAME "miner arguments"` command is supported. Ambiguous/complex scripts are refused for manual review. `--dry-run` prints the proposed script without modifying anything or stopping mining. Do not share that output if the wallet should remain private.

Validation: eight tests cover preserving CPU settings and worker suffixes, alternative miner binary names, equal-sign options, repeat application, ambiguous scripts, command-chain refusal, missing values, and worker-name input. Real pool connectivity must be verified on each rig after running.
