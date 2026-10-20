# Switch existing Alpine miners to SupportXMR

`switch-pool.py` updates the pool command in an existing `/etc/local.d/*.start` script. It retains the existing miner executable, copy/chmod commands, tmux session name, and non-pool options such as threads and CPU affinity. It does not deploy the 7945HX binary to other CPU models.

Run as root on each rig with Python 3.9 or newer:

```sh
python3 switch-pool.py --wallet YOUR_MONERO_ADDRESS
```

The script extracts a worker name from the suffix of the existing NiceHash username (`address.worker`). If none is recognised, it prompts for a name. Use `--worker NAME` to override it; use distinct names for separate rigs if separate dashboard entries are wanted. The wallet is an argument or an interactive input, not embedded in this repository. Format checking does not verify ownership or the address checksum.

The new connection is `pool.supportxmr.com:443`, TLS, rx/0, using the wallet as username and worker name as password. NiceHash-specific settings and previous pool options are removed. Existing CPU tuning is retained.

Before modifying startup settings, the script requires a mounted `/media/usb`, makes a timestamped startup-script backup there, and gracefully stops the matching tmux miner. It refuses to change startup settings if another miner remains running or the old session remains. It writes the updated script, runs `lbu commit`, syncs, starts the miner, and captures recent terminal output. Confirm new pool jobs and accepted shares afterward. It attempts to restore the original script and restart the previous miner if saving fails.

A simple single-line tmux command or direct miner command (optionally ending with `> /var/log/xmrig.log 2>&1 &`) is supported. Direct background startup is converted to tmux, and only the exact matching executable is signalled to stop. Ambiguous/complex scripts are refused for manual review. `--dry-run` prints the proposed script without modifying anything or stopping mining. Do not share that output if the wallet should remain private.

Validation: fifteen tests cover preserving CPU settings and worker suffixes, alternative miner binary names, equal-sign options, repeat application, ambiguous scripts, command-chain refusal, missing values, worker-name input, SupportXMR worker retention, download integrity, executable staging, successful installation, and rollback on save failure. Real pool connectivity must be verified on each rig after running.


## Optional miner upgrade

Pass `--miner-url URL --miner-sha256 SHA256` to upgrade the persistent executable while switching pools. The script identifies the persistent miner from its startup `cp` command, so both `/media/usb/xmrig` and `/media/usb/xmrig-miner` naming are supported. It remounts a read-only USB read/write, downloads to a separate file, verifies SHA-256, and runs `--version` before stopping mining or replacing the executable. A timestamped binary backup is kept on the USB. If saving fails, both the persistent binary and startup settings are restored.

The replacement must match the architecture, libc and runtime dependencies of the rigs. The generic Alpine body-align32 build is intended for these x86-64 Ryzen rigs; optional instruction paths remain CPU-gated, so older CPUs may use fallback paths. A version check is not a substitute for observing accepted pool shares on each CPU. The helper itself does not install runtime libraries; install the replacement's dependencies before running it. Download hashes must come from the intended source machine.

Existing SupportXMR worker names are recovered from the password when the username is a plain wallet. No CPU settings are changed by the upgrade.

Interactive prompts use `/dev/tty`, allowing the installer to be delivered through a Python heredoc. When no worker suffix or existing SupportXMR password can be recovered, type a short worker name at the prompt.
