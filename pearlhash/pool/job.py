"""Observed Pearlhash notify/header conversion, independent of vendor runtime.

The 200-byte field's first 76 bytes use a fixed XOR mapping, followed by a
repeating 32-byte mask. The remaining bytes are retained, not interpreted.
A decoded header is not a consensus validation. Version-marker and share-target
scaling semantics still require verification against a complete accepted job.
"""
from dataclasses import dataclass
import re
import struct

_HEADER_MASK = bytes.fromhex(
    '4dc0d47dff723cf8f75a583b596cf848f5106dd0d0aa7bdded9d4d566a929ffa'
    'abea8985cf34a26af1b118e2c697f283f0caadd643b0975390a17c79aae32e69'
    'cf166b57a6f64dd02914e7e4')
_SCRAMBLE_KEY = bytes.fromhex('9d2f73c411a85be0367ad14e920cbf65f32884da176eb941cc530fa67de21974')


def hex_bytes(value, size):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-fA-F]{'+str(size*2)+'}', value):
        raise ValueError('invalid fixed-width hexadecimal field')
    return bytes.fromhex(value)


def header_from_payload(payload):
    if not isinstance(payload, bytes) or len(payload) != 200:
        raise ValueError('expected 200-byte notify payload')
    return bytes(payload[i] ^ _HEADER_MASK[i] ^ _SCRAMBLE_KEY[i % 32] for i in range(76))


@dataclass(frozen=True)
class Notify:
    payload: bytes
    target_bytes: bytes
    token: bytes
    version_marker: str

    @classmethod
    def parse(cls, message):
        if not isinstance(message, dict) or message.get('status') != 1 or type(message.get('id')) is not int or message['id'] != -1:
            raise ValueError('expected successful pool notification')
        result = message.get('result')
        if not isinstance(result, list) or len(result) != 5 or result[0] != 'notify':
            raise ValueError('unsupported notify schema')
        if result[4] not in ('2', '3'):
            raise ValueError('unsupported version marker; do not infer a new consensus version')
        return cls(hex_bytes(result[1], 200), hex_bytes(result[2], 32), hex_bytes(result[3], 8), result[4])

    @property
    def header(self):
        return header_from_payload(self.payload)

    @property
    def header_fields(self):
        h = self.header
        version, = struct.unpack_from('<I', h)
        timestamp, nbits = struct.unpack_from('<II', h, 68)
        return {'version': version, 'previous_hash': h[4:36][::-1].hex(),
                'merkle_root': h[36:68][::-1].hex(), 'timestamp': timestamp, 'nbits': nbits}
