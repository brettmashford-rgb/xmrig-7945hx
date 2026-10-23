"""Offline PCAP/TCP/hex framing inspection; no network or field inference.

Usage: python3 tools/inspect_pool_capture.py capture.pcap --port 9000
Classic PCAP, Ethernet/SLL/SLL2, IPv4 TCP. Rejects gaps, conflicting overlaps,
fragments and truncation. Mid-session initial/final line boundaries are unknown.
Addresses, hex payloads and candidate plaintext are deliberately not printed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def payloads(data, port):
    magic = {b'\xd4\xc3\xb2\xa1': '<', b'\xa1\xb2\xc3\xd4': '>',
             b'\x4d\x3c\xb2\xa1': '<', b'\xa1\xb2\x3c\x4d': '>'}
    if len(data) < 24 or data[:4] not in magic:
        raise ValueError('not classic PCAP')
    endian = magic[data[:4]]
    link = struct.unpack_from(endian+'I', data, 20)[0]
    if link not in (1, 113, 276):
        raise ValueError('unsupported link type')
    pos, count, groups = 24, 0, {}
    while pos < len(data):
        if pos+16 > len(data):
            raise ValueError('truncated packet record')
        _, _, size, wire_size = struct.unpack_from(endian+'4I', data, pos)
        pos += 16
        if pos+size > len(data) or size != wire_size:
            raise ValueError('truncated packet')
        pkt = data[pos:pos+size]; pos += size; count += 1
        offset = {1: 14, 113: 16, 276: 20}[link]
        if len(pkt) < offset:
            raise ValueError('truncated link header')
        ethertype = struct.unpack_from('!H',pkt,{1:12,113:14,276:0}[link])[0]
        if ethertype in (0x8100,0x88a8):
            raise ValueError('VLAN framing not supported')
        if ethertype != 0x0800:
            continue
        if len(pkt) < offset+20 or pkt[offset]>>4 != 4:
            raise ValueError('invalid IPv4 header')
        ihl = (pkt[offset]&15)*4
        total, fragment = struct.unpack_from('!HH',pkt,offset+2)[0], struct.unpack_from('!H',pkt,offset+6)[0]
        if pkt[offset+9] != 6:
            continue
        if fragment & 0x3fff:
            raise ValueError('fragmented TCP unsupported')
        tcp = offset+ihl
        if ihl<20 or total<ihl+20 or offset+total>len(pkt):
            raise ValueError('invalid IPv4/TCP length')
        src, dst, seq = struct.unpack_from('!HHI',pkt,tcp)
        if port not in (src,dst):
            continue
        th = (pkt[tcp+12]>>4)*4
        if th<20 or ihl+th>total:
            raise ValueError('invalid TCP header')
        body = pkt[tcp+th:offset+total]
        syn = bool(pkt[tcp+13]&2)
        key = (pkt[offset+12:offset+20],src,dst)
        group = groups.setdefault(key, {'syn':False,'start':None,'parts':[]})
        if syn:
            if group['syn'] or group['parts']:
                raise ValueError('multiple sessions on one tuple unsupported')
            group['syn'] = True
            group['start'] = (seq+1)&0xffffffff
        if body:
            group['parts'].append(((seq+int(syn))&0xffffffff,body))
    return count, groups


def reassemble(parts):
    if not parts:
        return b''
    origin = parts[0][0]
    # Signed offsets also support a sequence-number wrap within a small capture.
    ordered = sorted((((seq-origin+0x80000000)&0xffffffff)-0x80000000,body)
                     for seq,body in parts)
    output = bytearray(); base = ordered[0][0]
    for offset,body in ordered:
        start = offset-base
        if start>len(output):
            raise ValueError('TCP sequence gap')
        overlap = min(len(body),len(output)-start)
        if output[start:start+overlap] != body[:overlap]:
            raise ValueError('conflicting TCP retransmission')
        output.extend(body[overlap:])
    return bytes(output)


def inspect(data, port=9000):
    packets, groups = payloads(data,port)
    streams=[]
    for (_,src,_),group in groups.items():
        if group['syn'] and group['parts']:
            start=group['start']
            first=min(((seq-start+0x80000000)&0xffffffff)-0x80000000
                      for seq,_ in group['parts'])
            if first!=0:
                raise ValueError('missing initial TCP bytes')
        body = reassemble(group['parts'])
        if not body:
            continue
        frames = body.split(b'\n')
        incomplete_tail = len(frames.pop())
        decoded=[]
        for frame in frames:
            # Do not accept whitespace or bytes.fromhex's permissive grammar.
            if not frame or len(frame)%2 or any(c not in b'0123456789abcdefABCDEF' for c in frame):
                raise ValueError('complete line is not strict ASCII hex')
            decoded.append(bytes.fromhex(frame.decode('ascii')))
        pattern=[]
        for raw in decoded:
            # A descriptive bit statistic, not evidence of a cipher or field.
            if len(raw)>=128:
                sample=raw[4:]
                agree=sum(((a^b)&128)==0 for a,b in zip(sample[48:],sample))
                pattern.append({'decoded_bytes':len(raw),'lag':48,'skip':4,
                                'high_bit_agreement':agree/(len(sample)-48)})
        streams.append({'direction':'pool_to_miner' if src==port else 'miner_to_pool',
                        'syn_seen':group['syn'],'first_line_boundary_verified':group['syn'],
                        'decoded_line_lengths':list(map(len,decoded)),
                        'incomplete_tail_bytes':incomplete_tail,'pattern_statistics':pattern})
    return {'sha256':hashlib.sha256(data).hexdigest(),'packets':packets,'streams':streams}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pcap',type=Path);parser.add_argument('--port',type=int,default=9000)
    args=parser.parse_args()
    print(json.dumps(inspect(args.pcap.read_bytes(),args.port),indent=2))
