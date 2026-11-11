#!/usr/bin/env bash
set -Eeuo pipefail
printf 'Downloading and verifying v70 and v71 launchers...\n'
work=$(mktemp -d /tmp/pearl-v070-v071.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
python3 - "$work" <<'PYTHON'
import hashlib,pathlib,sys,urllib.request
folder=pathlib.Path(sys.argv[1])
versions={70: 'c9aac80ede303d890f8df20a6603651d471ba276d608eed1c8c2d7a56ce6af82', 71: 'a84366ff6f24a4c84f477104aea60f62748ce3faacc423dc5dad57f77004e7e7'}
for version,expected in versions.items():
    name=f'run_v{version:03d}.sh'
    url='https://raw.githubusercontent.com/brettmashford-rgb/xmrig-7945hx/main/pearlhash/tools/'+name
    with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(1048577)
    if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit('STOP: '+name+' checksum mismatch')
    (folder/name).write_bytes(raw)
    print(name+' checksum verified.',flush=True)
PYTHON
printf '\n========== v70 cooperative B-sharing test ==========\n'
bash "$work/run_v070.sh"
printf '\n========== v71 transcript-fold test ==========\n'
bash "$work/run_v071.sh"
printf '\nBoth launchers finished. Send CTA B COMPARISON and PARTITION FOLD COMPARISON plus KERNEL RESOURCES.\n'
