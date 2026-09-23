"""Bounded GGUF v3 little-endian metadata/tensor inventory, not a model loader.

Reference: ggml-org/ggml/docs/gguf.md. Only explicitly listed tensor types
are sized. Unknown types and split files fail closed. No weight data is read.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import struct
from pathlib import Path

from .io import ContractError, integer, require, stable_file

# ggml_type -> (elements/block, bytes/block); packed row layout, NOT traffic.
TYPE_SIZES = {0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20),
              6: (32, 22), 7: (32, 24), 8: (32, 34), 10: (256, 84),
              11: (256, 110), 12: (256, 144), 13: (256, 176),
              14: (256, 210), 15: (256, 292), 30: (1, 2)}
SCALARS = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i',
           6: 'f', 7: 'B', 10: 'Q', 11: 'q', 12: 'd'}


class Reader:
    def __init__(self, fd: int, size: int, budget: int):
        self.fd, self.size, self.budget, self.offset = fd, size, budget, 0
        self.values = 0
        self.hasher = hashlib.sha256()

    def read(self, n: int) -> bytes:
        require(0 <= n <= self.size - self.offset, 'truncated GGUF')
        require(n <= self.budget - self.offset, 'GGUF metadata byte budget exceeded')
        data = os.pread(self.fd, n, self.offset)
        require(len(data) == n, 'GGUF short read')
        self.offset += n
        self.hasher.update(data)
        return data

    def number(self, fmt: str):
        return struct.unpack('<' + fmt, self.read(struct.calcsize('<' + fmt)))[0]

    def string(self, limit: int = 1 << 20) -> str:
        n = self.number('Q')
        require(n <= limit, 'GGUF string too large')
        try:
            return self.read(n).decode('utf-8')
        except UnicodeError as exc:
            raise ContractError('invalid GGUF UTF-8') from exc

    def value(self, kind: int, depth: int = 0):
        self.values += 1
        require(depth <= 8 and self.values <= 2_000_000, 'GGUF metadata complexity exceeded')
        if kind == 8:
            return self.string()
        if kind == 9:
            sub, n = self.number('I'), self.number('Q')
            require(n <= 1_000_000 and sub in {*SCALARS, 8, 9}, 'invalid GGUF array')
            # Consume/validate but never retain tokenizer arrays or giant arrays.
            for _ in range(n):
                self.value(sub, depth + 1)
            return {'array_type': sub, 'array_length': n}
        require(kind in SCALARS, 'unknown GGUF metadata type')
        v = self.number(SCALARS[kind])
        if kind == 7:
            require(v in (0, 1), 'invalid GGUF bool')
            return bool(v)
        if kind in (6, 12):
            require(math.isfinite(v), 'non-finite GGUF metadata')
        return v


def inspect(path: str | Path, metadata_budget: int = 64 << 20) -> dict:
    integer(metadata_budget, 'metadata budget', 24, 128 << 20)
    with stable_file(path) as (fd, st):
        r = Reader(fd, st.st_size, metadata_budget)
        require(r.read(4) == b'GGUF', 'not a GGUF file')
        require(r.number('I') == 3, 'only GGUF v3 little-endian is supported')
        nt, nk = r.number('Q'), r.number('Q')
        require(0 < nt <= 100_000 and nk <= 100_000, 'GGUF counts outside limits')
        metadata = {}
        for _ in range(nk):
            key = r.string(65535)
            require(re.fullmatch(r'[a-z0-9_]+(?:\.[a-z0-9_]+)*', key) is not None,
                    'invalid metadata key')
            require(key not in metadata, 'duplicate GGUF metadata key')
            metadata[key] = r.value(r.number('I'))
        require(type(metadata.get('general.architecture')) is str, 'missing architecture')
        split_count = metadata.get('split.count', 1)
        require(type(split_count) is int and split_count == 1, 'split GGUF not admitted')
        alignment = integer(metadata.get('general.alignment', 32), 'alignment', 1, 4096)
        require(alignment & (alignment - 1) == 0, 'alignment is not a power of two')
        tensors, names = [], set()
        for _ in range(nt):
            name = r.string(64)
            require(name and '\x00' not in name and name not in names, 'invalid/duplicate tensor')
            names.add(name)
            ndim = integer(r.number('I'), 'dimensions', 1, 4)
            shape = [integer(r.number('Q'), 'dimension', 1, 2**31) for _ in range(ndim)]
            kind, offset = r.number('I'), r.number('Q')
            require(kind in TYPE_SIZES, f'unsupported tensor type {kind}; no inferred byte size')
            block, nbytes = TYPE_SIZES[kind]
            require(shape[0] % block == 0, 'quantized row not block-aligned')
            size = math.prod(shape) // block * nbytes
            require(size <= st.st_size and offset % alignment == 0, 'invalid tensor size/offset')
            tensors.append({'name': name, 'shape': shape, 'type_id': kind,
                            'relative_offset': offset, 'encoded_bytes': size})
        data_start = (r.offset + alignment - 1) // alignment * alignment
        r.read(data_start - r.offset)
        end = data_start
        for tensor in sorted(tensors, key=lambda t: t['relative_offset']):
            start = data_start + tensor['relative_offset']
            require(start >= end, 'overlapping tensors')
            end = start + tensor['encoded_bytes']
            require(end <= st.st_size, 'tensor outside file')
            tensor['file_offset'] = start
        arch = metadata['general.architecture']
        ec = metadata.get(arch + '.expert_count')
        active = metadata.get(arch + '.expert_used_count')
        if ec is not None or active is not None:
            integer(ec, 'expert count', 1, 1_000_000)
            integer(active, 'active experts', 1, ec)
        total = sum(t['encoded_bytes'] for t in tensors)
        expert_bytes = sum(t['encoded_bytes'] for t in tensors if '_exps.' in t['name'])
        # Summaries only; arrays are consumed, not exposed as tokenizer content.
        selected = {k: v for k, v in metadata.items()
                    if not k.startswith('tokenizer.') and type(v) is not dict}
        return {'schema': 'tesy.gguf-inventory.v1', 'classification': 'STATIC_ONLY',
                'architecture': arch, 'file_bytes': st.st_size,
                'header_bytes_read': r.offset, 'header_sha256': r.hasher.hexdigest(),
                'weights_read': False, 'model_loaded': False,
                'tensor_count': nt, 'tensor_data_offset': data_start,
                'encoded_tensor_bytes': total, 'expert_tensor_bytes_by_name': expert_bytes,
                'expert_count': ec, 'active_experts': active,
                'is_moe_metadata': ec is not None, 'metadata': selected, 'tensors': tensors,
                'physical_traffic_measured': False, 'qualification': False}
