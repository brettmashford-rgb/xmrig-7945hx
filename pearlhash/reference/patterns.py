"""Canonical Pearl periodic index patterns (ISC).

Independent implementation of pinned proof_utils.rs rules at
82e6eee7076aafe10123e08db78f100d270c0582. Not a complete consensus validator.
Expansion capped at 256 indices (the pinned maximum total jackpot tile size).
"""
from dataclasses import dataclass
from math import prod


@dataclass(frozen=True)
class PeriodicPattern:
    encoded: bytes

    def __post_init__(self):
        if type(self.encoded) is not bytes or len(self.encoded) != 6:
            raise ValueError('pattern must be six bytes')
        minimum, done = 1, False
        for i in range(0, 6, 2):
            factor, length = self.encoded[i]+1, self.encoded[i+1]+1
            if length == 1 or done:
                if (factor, length) != (1, 1):
                    raise ValueError('noncanonical inactive dimension')
                done = True
            elif factor == 1 and minimum != 1:
                raise ValueError('a single stride must not be split')
            if minimum * factor * length > 1 << 24:
                raise ValueError('pattern period exceeds 2^24')
            minimum *= factor * length
        if self.size > 256:
            raise ValueError('prototype expansion cap: 256 indices')

    @property
    def shape(self):
        minimum, result = 1, []
        for i in range(0, 6, 2):
            stride, length = minimum * (self.encoded[i]+1), self.encoded[i+1]+1
            result.append((stride, length))
            minimum = stride * length
        return tuple(result)

    @property
    def size(self):
        return prod(self.encoded[i]+1 for i in (1, 3, 5))

    @property
    def period(self):
        stride, length = self.shape[-1]
        return stride * length

    def to_list(self):
        result = [0]
        for stride, length in self.shape:
            result = [value+i*stride for i in range(length) for value in result]
        return result

    def offset_is_valid(self, offset):
        if type(offset) is not int or not 0 <= offset <= 0xffffffff:
            raise ValueError('offset must be u32')
        for stride, length in reversed(self.shape):
            offset %= stride * length
            if offset >= stride:
                return False
        return True

    def indices_with_offset(self, offset):
        if not self.offset_is_valid(offset):
            raise ValueError('invalid pattern offset')
        result = [offset+value for value in self.to_list()]
        if result[-1] > 0xffffffff:
            raise ValueError('index exceeds u32')
        return result

    @classmethod
    def from_list(cls, values):
        values = list(values)
        if not values or len(values) > 256:
            raise ValueError('expected 1..256 indices')
        if any(type(v) is not int or not 0 <= v <= 0xffffffff for v in values):
            raise ValueError('indices must be u32')
        if values[0] != 0 or any(a >= b for a, b in zip(values, values[1:])):
            raise ValueError('indices must start at zero and be strictly increasing')
        remaining, dimensions = values[:], []
        while len(remaining) > 1:
            for period in range(1, len(remaining)):
                if len(remaining) % period:
                    continue
                stride = remaining[period]
                if all(a+stride == b for a, b in zip(remaining, remaining[period:])):
                    dimensions.append((stride, len(remaining)//period))
                    remaining = remaining[:period]
                    break
            else:
                raise ValueError('indices are not periodic')
        dimensions.reverse()
        if len(dimensions) > 3:
            raise ValueError('more than three pattern dimensions')
        period = dimensions[-1][0]*dimensions[-1][1] if dimensions else 1
        dimensions += [(period, 1)] * (3-len(dimensions))
        minimum, encoded = 1, bytearray()
        for stride, length in dimensions:
            if stride % minimum or not 1 <= stride//minimum <= 256 or not 1 <= length <= 256:
                raise ValueError('pattern cannot be represented canonically')
            encoded.extend((stride//minimum-1, length-1))
            minimum = stride * length
        result = cls(bytes(encoded))
        if result.to_list() != values:
            raise ValueError('pattern reconstruction mismatch')
        return result
