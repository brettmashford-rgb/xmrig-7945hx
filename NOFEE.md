# Reciprocal JIT build with developer donation disabled

This build keeps the reciprocal-multiply JIT rewrite and AES prefetch distance 7168. It disables XMRig developer-pool donation mining.

- In src/donate.h, default and minimum donation levels become zero.
- Pools::setDonateLevel always stores zero. Existing JSON or CLI donation values, including positive ones and later configuration reloads, cannot enable donation in this binary.
- Pools::donateLevel consequently reports zero. Network creates DonateStrategy only when this level is positive, so the developer-pool strategy is not instantiated.
- Copyright and licence notices remain intact. This does not alter fees charged by the user's selected pool or platform.

The original builds remain available. This script uses its own source/output trees and does not install, start or replace any pool miner.

## Alpine build

From the repository folder, enter separately:

```sh
git pull --ff-only
sh build-jit-rcp-nofee.sh
```

Output: .work/build-7168-jit-rcp-nofee/xmrig

Use this executable with the existing pool, wallet and worker arguments. No extra donation flag is required. Pool mining startup should display DONATE 0%. Benchmark mode already forces donation to zero upstream, so a benchmark's 0% display alone cannot establish that donation is disabled during pool mining.

## Validation and limits

The complete configuration translation unit compiled locally both with benchmark support enabled and disabled. Component checks of the actual compiled Pools constructor, level setter and getter passed for default construction and requests INT_MIN, -1, 0, 1, 2, 50, 99, 100 and INT_MAX. Donation remained zero. Source inspection confirmed the configuration reader routes donation values through that setter and that Network's donation strategy creation is gated by the reported level.

The combined pinned-source patch applies cleanly and matches the resulting canonical git diff. Shell syntax passes. The reciprocal/AES implementation in this combined patch is the same as the prior reciprocal experiment; fee changes are confined to the donation defaults and configuration setter. The new full no-fee binary has not been linked or run on Alpine here; target build and live pool operation remain to be checked. No new benchmark speed claim is made.
