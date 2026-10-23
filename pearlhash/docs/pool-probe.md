# Login-only Pearlhash diagnostic

`tools/pool_probe.py` uses Python standard library only. It connects once to
pool.pearlhash.xyz:9000, sends one login under our own agent name and the distinct
5060-dev-probe worker, receives login/extranonce/notify, then closes. A successful
result proves only independent outer transport and login compatibility. No
scrambled job layout, target/version semantics, mining or share acceptance is
established. The tool has no GPU/service/clock code, share command or reconnect.

CLI arguments: `--wallet ADDRESS --worker NAME --output NEW_LOCAL_JSON_PATH`.
Output must not already exist; its parent must exist. The JSON transcript is
created mode 0600 and remains on the rig. No automatic upload occurs. The
receive exchange is bounded by 30 seconds, 16 messages and 64 KiB per frame;
DNS resolution follows system resolver timeouts. Connection timeout is ten
seconds. Errors preserve messages already received and return nonzero.

Run while WildRig/XMRig continue. Save a screenshot of the console result for
review before proceeding. Do not publish private transcripts. The tool does
not require nvcc, cargo, package installation or root.

Tests: from pearlhash/, run unittest discovery with pattern test_pool*.py.
These use synthetic data and an in-memory fake socket, with no pool contact.
Outer codec reconstruction/evidence and remaining blockers are recorded in
[pool-capture-findings.md](pool-capture-findings.md).
