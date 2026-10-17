#!/usr/bin/env python3
"""Join perf's monotonic timestamps/IPs to the correct recorded JIT version."""
import argparse
import bisect
import collections
import re
import struct
import subprocess
import tempfile
from pathlib import Path

HEADER = struct.Struct('<8sII')
RECORD = struct.Struct('<QQIIIIII')
REGION = struct.Struct('<III')
KINDS = ('IADD_RS IADD_M ISUB_R ISUB_M IMUL_R IMUL_M IMULH_R IMULH_M '
         'ISMULH_R ISMULH_M IMUL_RCP INEG_R IXOR_R IXOR_M IROR_R IROL_R '
         'ISWAP_R FSWAP_R FADD_R FADD_M FSUB_R FSUB_M FSCAL_R FMUL_R '
         'FDIV_M FSQRT_R CBRANCH CFROUND ISTORE NOP PROLOGUE SCRATCHPAD_LOAD '
         'DATASET_ADDRESS DATASET_READ UNUSED LOOP_TAIL EPILOGUE').split()


def records(path, data=True):
    with open(path, 'rb') as f:
        head = f.read(HEADER.size)
        if len(head) != HEADER.size or HEADER.unpack(head)[0] != b'RXJIT01\0':
            raise ValueError('Invalid or incomplete trace header')
        while True:
            raw = f.read(RECORD.size)
            if not raw:
                return
            if len(raw) != RECORD.size:
                raise ValueError('Truncated trace record header')
            stamp, base, size, epi_offset, epi_size, count, tid, reserved = RECORD.unpack(raw)
            if count > 4096 or size > 65536 or epi_size > 65536 or reserved:
                raise ValueError('Invalid trace record size')
            if size == 0:
                yield dict(stamp=stamp, end=True, tid=tid)
                return
            amount = count * REGION.size + size + epi_size
            if data:
                raw = f.read(amount)
                if len(raw) != amount:
                    raise ValueError('Truncated trace payload')
                regions = [REGION.unpack_from(raw, i * REGION.size) for i in range(count)]
                previous = 0
                for begin, end, kind in regions:
                    if not previous <= begin < end <= size or kind >= 36:
                        raise ValueError('Invalid/overlapping instruction regions')
                    previous = end
                code = raw[count * REGION.size:count * REGION.size + size]
                epilogue = raw[-epi_size:] if epi_size else b''
            else:
                f.seek(amount, 1)
                if f.tell() > path.stat().st_size:
                    raise ValueError('Truncated trace payload')
                regions, code, epilogue = [], b'', b''
            yield dict(stamp=stamp, base=base, size=size, epi_offset=epi_offset,
                       epi_size=epi_size, regions=regions, starts=[r[0] for r in regions],
                       code=code, epilogue=epilogue, tid=tid, end=False)


def samples(path):
    # perf script -F tid,time,ip --ns: TID seconds.nanoseconds: hex_ip
    pattern = re.compile(r'^\s*(\d+)\s+(\d+)\.(\d+):?\s+([0-9a-fA-F]+)\s*$')
    result = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        m = pattern.match(line)
        if not m:
            raise ValueError('Unexpected perf sample format: ' + line[:160])
        tid, sec, frac, ip = m.groups()
        if len(frac) > 9:
            raise ValueError('Unexpected timestamp precision')
        result.append((int(sec) * 1000000000 + int(frac.ljust(9, '0')), int(tid), int(ip, 16)))
    return sorted(result)


def analyze(trace_path, sample_path, output):
    with open(trace_path, 'rb') as trace_file:
        raw = trace_file.read(HEADER.size)
    if len(raw) != HEADER.size or HEADER.unpack(raw)[0] != b'RXJIT01\0':
        raise ValueError('Invalid or incomplete trace header')
    magic, pid, owner = HEADER.unpack(raw)
    end = 0
    versions = 0
    first = None
    last_stamp = -1
    for record in records(trace_path, data=False):
        if record['tid'] != owner or record['stamp'] < last_stamp:
            raise ValueError('Trace thread or timestamp mismatch')
        last_stamp = record['stamp']
        end = record['stamp']
        if not record['end']:
            first = record['stamp'] if first is None else first
            versions += 1
    if not versions:
        raise ValueError('No JIT programs captured')
    # Exclude samples at/after the terminal marker. Without one, conservatively
    # exclude the final version because its lifetime has no recorded endpoint.
    source = iter(records(trace_path))
    upcoming = next(source, None)
    latest = {}
    counts = collections.Counter()
    examples = collections.defaultdict(list)
    selected = outside = other_thread = 0
    for stamp, tid, ip in samples(sample_path):
        if tid != owner:
            other_thread += 1
            continue
        if not first <= stamp < end:
            continue
        while upcoming and upcoming['stamp'] <= stamp:
            if not upcoming['end']:
                latest[upcoming['base']] = upcoming
            upcoming = next(source, None)
        selected += 1
        found = None
        for base, record in latest.items():
            offset = ip - base
            if 0 <= offset < record['size']:
                index = bisect.bisect_right(record['starts'], offset) - 1
                if index >= 0:
                    begin, finish, kind = record['regions'][index]
                    if begin <= offset < finish:
                        found = kind, record['code'][begin:finish], offset - begin
            elif record['epi_offset'] <= offset < record['epi_offset'] + record['epi_size']:
                found = 36, record['epilogue'], offset - record['epi_offset']
            if found:
                break
        if not found:
            outside += 1
            continue
        kind, code, offset = found
        counts[kind] += 1
        if len(examples[kind]) < 3:
            examples[kind].append((code, offset))
    mapped = sum(counts.values())
    if not mapped:
        raise ValueError('No samples mapped: check perf clock, thread and trace coverage')
    lines = [f'Profiled worker TID: {owner}', f'Code versions captured: {versions}',
             f'Capture coverage: {(end-first)/1e9:.3f} seconds',
             f'Owner-thread samples in coverage: {selected}', f'Mapped JIT samples: {mapped}',
             f'Owner-thread samples outside recorded JIT: {outside}',
             '', 'Share of mapped JIT samples by emitted region:', '']
    lines += [f'{100*count/mapped:6.2f}%  {count:7d}  {KINDS[kind]}' for kind, count in counts.most_common()]
    lines += ['', 'These are sampled-IP shares, not instruction latency or cycle costs.',
              'Sampling skid and tracing overhead can bias results. CFROUND regions may',
              'include NOPs from eliminated updates. Use machine-code examples to inspect them.',
              'No speed or wall-power conclusion can be drawn from this diagnostic run.']
    output.mkdir(parents=True, exist_ok=True)
    summary = '\n'.join(lines) + '\n'
    (output / 'summary.txt').write_text(summary)
    asm = []
    for kind, _ in counts.most_common(12):
        for index, (code, offset) in enumerate(examples[kind], 1):
            with tempfile.NamedTemporaryFile() as temp:
                temp.write(code); temp.flush()
                text = subprocess.check_output(['objdump', '-D', '-b', 'binary', '-m',
                                                'i386:x86-64', temp.name], text=True)
            asm.append(f'\n{KINDS[kind]} example {index}; sampled offset +0x{offset:x}\n{text}')
    (output / 'hot-examples.txt').write_text(''.join(asm))
    print(summary)
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        analyze(args.directory / 'jit-trace.bin', args.directory / 'samples.txt', args.directory)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
