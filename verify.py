#!/usr/bin/env python3
"""Compare the changed hardware-AES routine against unmodified git HEAD."""
import hashlib, pathlib, subprocess, tempfile, sys
root = pathlib.Path(sys.argv[1]).resolve()
profile = sys.argv[2] if len(sys.argv) > 2 else 'generic'
if profile not in ('generic', 'zen4', 'zen4-lto'):
    raise SystemExit('profile must be generic, zen4 or zen4-lto')
extra = [] if profile == 'generic' else ['-march=znver4', '-mtune=znver4', '-Ofast']
link_flags = ['-flto=2'] if profile == 'zen4-lto' else []
extra += link_flags
here = pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    original = subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:src/crypto/randomx/aes_hash.cpp'])
    (tmp/'original.cpp').write_bytes(original)
    base = ['g++','-std=c++11','-O2','-maes','-ffunction-sections','-fdata-sections', '-I'+str(root/'src'), '-I'+str(root/'src/3rdparty')]
    subprocess.run(base+['-c', str(here/'check.cpp'), '-o', str(tmp/'check.o')], check=True)
    reference = None
    for distance in [None,256,1024,2048,4096,6144,7168,8192]:
        source = tmp/'original.cpp' if distance is None else root/'src/crypto/randomx/aes_hash.cpp'
        flags = [] if distance is None else ['-DXMRIG_RX_AES_PREFETCH_DISTANCE='+str(distance)]
        subprocess.run(base+flags+([] if distance is None else extra)+['-c', str(source), '-o', str(tmp/'aes.o')], check=True)
        subprocess.run(['g++']+link_flags+['-Wl,--gc-sections',str(tmp/'check.o'),str(tmp/'aes.o'),'-o',str(tmp/'check')], check=True)
        digest = hashlib.sha256(subprocess.check_output([str(tmp/'check')])).hexdigest()
        if reference is None: reference = digest
        assert digest == reference, (distance,digest,reference)
        print(profile+' '+str(distance or 'upstream')+': PASS '+digest, flush=True)
    for distance in [0,255,257,8448]:
        result = subprocess.run(base+['-DXMRIG_RX_AES_PREFETCH_DISTANCE='+str(distance),'-c',str(root/'src/crypto/randomx/aes_hash.cpp'),'-o',str(tmp/'invalid.o')], capture_output=True)
        assert result.returncode and b'AES prefetch distance must' in result.stderr
        print(str(distance)+': correctly rejected', flush=True)
