# RCP build with donation subsystem removed

Run from the experiment repository on Alpine:

```sh
git pull --ff-only
sh build-jit-rcp-nofee.sh
```

Output: `.work/build-7168-jit-rcp-nodonate/xmrig`.

This is a separate source and build directory, including from the earlier forced-zero experiment. It retains the reciprocal-multiply JIT rewrite, generic compiler settings, prefetch distance 7168 and no LTO. The script neither installs nor starts the miner.

The combined patch deletes DonateStrategy.cpp, DonateStrategy.h and donate.h; removes donation source entries from CMake, donation scheduling and share-routing hooks from Network, and donation job switching from Miner. It also removes donation configuration fields, command-line options, help text, startup display and API metadata. The supplied example and embedded default configurations have no developer-pool address; specify your own pool as usual.

Existing JSON donation fields are ignored because there is no parser or strategy for them. Remove old --donate-level or --donate-over-proxy command-line arguments: these options no longer exist. Normal user pool selection and configured failover remain supported. Licenses and copyright notices are retained.

Validation: the combined patch applies to the pinned clean XMRig v6.26.0 revision and reproduces its canonical diff. A complete Linux CPU miner build with TLS, HTTP/API and benchmark enabled links successfully. CLI help and the binary contain none of the removed donation options, strategy name, built-in donation hostnames or donation-start message. An offline 250K rx/0 run matches checksum 7D6054757BB08A63. The Alpine script passes shell syntax checking; the full Alpine HWLOC/MSR build remains to run on the target. No live pool connection was used for validation.
