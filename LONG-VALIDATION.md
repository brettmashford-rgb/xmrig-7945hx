# Longer experiment validation

run-experiment.py accepts --bench 1M (default) or --bench 10M. The expected rx/0 checksums are taken from the pinned upstream BenchState_test.h: 898B6E0431C28A6B for 1M, B5231262E2792B26 for 10M. The 10M timeout is 1800 seconds; 1M retains 900 seconds. Results record the selected hash count and checksum; terminal and text summaries show the selected length.

For the already-built register-mask candidate, with the pool miner stopped:

    python3 run-experiment.py register-mask --skip-build --bench 10M

Omit --skip-build to rebuild first. No binary or startup changes are installed. The runner stops only its own benchmark process group after completion. Compare runs at unchanged hardware settings and observe wall power during the sustained portion.

Validation: Python compilation and CLI help passed. Mocked end-to-end runner checks cover default 1M and explicit 10M selection, expected checksum and hash-count recording, rejection of a 1M checksum in a 10M run, timeout selection, measured-power arithmetic and reuse of the selected existing binary. Miner code is unchanged.
