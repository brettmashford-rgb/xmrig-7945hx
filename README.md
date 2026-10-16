# XMRig 7945HX prefetch experiment for Alpine

Experimental tuning of XMRig v6.26.0. No measured speedup is claimed.
Baseline target: 17,300 H/s at 100 W at the wall (173 H/s/W).

The script downloads the official source at a fixed revision, applies the
included patch, then builds it on Alpine. It leaves the existing miner alone.

On your Alpine machine, run these first commands as root:

```sh
apk add --no-cache git ca-certificates
git clone https://github.com/brettmashford-rgb/xmrig-7945hx.git
cd xmrig-7945hx
sh build-alpine.sh 7168
sh build-alpine.sh 4096
sh build-alpine.sh 2048
```

Run from a directory containing the script and aes-prefetch.patch. As root, the
script installs build dependencies with apk. It builds with two jobs by default
to limit RAM use; override with JOBS=4 if desired. Packages come from your
existing Alpine repositories. Builds are dynamically linked for that Alpine
system, not promised portable to different releases.

Build outputs are .work/build-7168/xmrig, .work/build-4096/xmrig and
.work/build-2048/xmrig. The script prints versions but never starts mining,
changes autostart, runs lbu commit, or replaces the existing installation.
Diskless changes may disappear at reboot: choose a persistence location before
installing a winning build. Do not add the whole build tree to the boot backup.

Read EXPERIMENT.md for component test results and the full performance test plan.
The generic builds have been built and benchmarked by the user on Alpine. The new Zen 4 profiles still require a full Alpine build and end-to-end benchmark.
The build script passes sh syntax checking; compiler checks in verify.py cover
the changed AES component only. Validate the complete rx/0 benchmark checksum
before using a changed miner with a pool.

Upstream source and license: https://github.com/xmrig/xmrig/tree/v6.26.0
Official Alpine instructions: https://xmrig.com/docs/miner/build/alpine
The distributed patch is licensed under GPL-3.0-or-later, consistent with XMRig.
The upstream source download retains its original license notices. The original
build and verification scripts in this repository are also GPL-3.0-or-later.

## After building

Start with the 7168 build as the default-distance baseline. Use identical
settings for subsequent candidate comparisons. These commands perform an
offline rx/0 benchmark rather than connecting to a pool:

```sh
.work/build-7168/xmrig --bench=1M --algo=rx/0
.work/build-4096/xmrig --bench=1M --algo=rx/0
```

Confirm the miner reports a valid benchmark checksum. A short benchmark is a
correctness check, not sufficient proof of a sustained performance gain. Use
repeated longer comparisons with wall-power measurements for that decision.

Current verification: byte-for-byte AES component equivalence at seven
distances; shell syntax and invalid-argument checks. The user has built and run the generic profile on Alpine. The new Zen 4 profiles
have not yet been built as complete miners or benchmarked on Alpine.

## Zen 4 compiler experiment

Keep prefetch at 7168 while changing compiler options. From this repository on
the 7945HX:

```sh
git pull --ff-only
sh build-alpine.sh 7168 zen4
.work/build-7168-zen4/xmrig --bench=10M --algo=rx/0
```

The zen4 profile uses GCC with `-march=znver4 -mtune=znver4`. LTO is explicitly
OFF. The optional next experiment adds only LTO:

```sh
sh build-alpine.sh 7168 zen4-lto
.work/build-7168-zen4-lto/xmrig --bench=10M --algo=rx/0
```

The LTO profile uses CMake's interprocedural optimisation setting. Existing
commands with no profile argument still select generic and keep the existing
output paths. New profile builds are stored separately and never overwrite the
baseline, install a service or start mining. Changing profiles does not change
the RandomX JIT's algorithm or instruction rules. Performance gains are not
promised: a large portion of the hash loop is generated machine code.

These binaries target Zen 4. Do not deploy them to the 3900X or 5900X. Keep the
same power limit, cooling, thread selection and benchmark length for comparisons.
Use a matching checksum and repeated runs before judging tiny speed differences.
Measure wall power during each candidate run; unchanged power has not yet been
established for these new profiles.

User-reported 10M results before this experiment:

| Profile | Prefetch | H/s | Runs |
|---|---:|---:|---:|
| generic | 7168 | 17336.6 | 1 |
| generic | 6144 | 17350.0 | 1 |

The second result was sent after instructions to test 6144; its screenshot did
not include the executable command. A 0.077% difference does not establish a
repeatable gain, so the default 7168 remains the comparison setting.

GCC CPU options: https://gcc.gnu.org/onlinedocs/gcc/x86-Options.html
CMake IPO setting: https://cmake.org/cmake/help/latest/variable/CMAKE_INTERPROCEDURAL_OPTIMIZATION.html

Local verification of the new profiles: both Zen 4 and Zen 4 plus LTO produced
byte-identical hash, fill state and scratchpad output against generic upstream
in all 48 AES cases at each of seven prefetch distances. These checks used GCC
13.3 on a shared EPYC host with the relevant instruction support. Shell syntax
and four invalid profile/argument cases also passed. This is component
verification, not a full Alpine miner build or a target performance benchmark.
Reproduce with `python3 verify.py /path/to/patched/upstream zen4` or `zen4-lto`.

## Alpine LTO link compatibility

The first user build of zen4-lto failed in Alpine fortify's always-inline
snprintf wrapper, instantiated by bundled fmt formatting code. The LTO profile
now uses cmake/alpine-lto.cmake to compile only src/3rdparty/fmt/format.cc with
-fno-lto. The rest of the miner retains IPO/LTO, and fortify remains enabled.
The generic and zen4 profiles are unchanged. The comparison is therefore LTO
with this formatting-library exclusion, not LTO on every translation unit.

To retry after a failed LTO build, pull this update and rerun the same build
command. CMake should detect the changed per-source option and rebuild fmt;
there is no need to remove the source tree or working baseline builds. Run
the benchmark only after the script finishes successfully and prints a version.
This workaround still needs full linking verification on the user's Alpine
GCC 15.2 toolchain. A local mixed LTO/non-LTO formatting link check validates
that the formatting object is conventional native code and links with LTO code,
but does not reproduce Alpine's fortified headers.

## Source-level JIT experiment

The separate [JIT division-mask rewrite](JIT-TERNARY.md) combines an AND/OR instruction pair using AVX-512 on Zen 4. Component correctness tests pass; mining performance is unproven. Build with `sh build-jit-ternary.sh`. The generic baseline remains available.
