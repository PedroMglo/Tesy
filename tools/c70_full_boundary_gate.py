#!/usr/bin/env python3
"""C70 full P12 wave-skip active-state and parked-pair contract."""
from collections import defaultdict
import csv
from pathlib import Path
import struct

from c2_gate import GateError
import c7_boundary_gate as c7


def _index(root):
    with (root / 'index.tsv').open(newline='') as source:
        reader = csv.DictReader(source, delimiter='\t')
        if reader.fieldnames != c7.INDEX_FIELDS:
            raise GateError('C70 index header changed')
        return list(reader)


def _values(root, row):
    ne = tuple(map(int, row['ne'].split(',')))
    nb = tuple(map(int, row['nb'].split(',')))
    if len(ne) != 4 or len(nb) != 4 or any(v <= 0 for v in ne + nb):
        raise GateError('C70 wave shape/stride invalid')
    data = (root / row['file']).read_bytes()
    dtype = '<i' if row['type'] == 'i32' else '<f'
    return [struct.unpack_from(dtype, data, sum(i*s for i, s in zip(
        (i0, i1, i2, i3), nb)))[0]
        for i3 in range(ne[3]) for i2 in range(ne[2])
        for i1 in range(ne[1]) for i0 in range(ne[0])]


def inspect(root, *, skip_on):
    root = Path(root)
    logits, coverage = c7.capture(root, allow_parked=skip_on)
    core = {}
    waves = defaultdict(lambda: {'ffn_moe_wave_ids': [], 'ffn_moe_wave_mask': []})
    for row in _index(root):
        key = (row['phase'], int(row['layer']))
        if row['name'] in c7.CORE:
            stage_key = (*key, row['name'])
            if stage_key in core:
                raise GateError('C70 duplicate core stage')
            core[stage_key] = (root / row['file']).read_bytes()
        if row['name'] in ('ffn_moe_wave_ids', 'ffn_moe_wave_mask'):
            wave = row['name']
            ne = tuple(map(int, row['ne'].split(',')))
            if row['type'] != ('i32' if wave.endswith('ids') else 'f32') or \
               ne != ((4, int(row['state_tokens']), 1, 1) if wave.endswith('ids')
                      else (1, 4, int(row['state_tokens']), 1)):
                raise GateError('C70 wave dtype/shape changed')
            waves[key][wave].append(_values(root, row))
    sentinels = 0
    masks = {}
    for key, tensors in waves.items():
        ids = tensors['ffn_moe_wave_ids']
        mask = tensors['ffn_moe_wave_mask']
        if len(ids) != len(mask) or not ids:
            raise GateError('C70 wave ID/mask pair incomplete')
        masks[key] = mask
        for id_row, mask_row in zip(ids, mask):
            if len(id_row) != len(mask_row):
                raise GateError('C70 wave ID/mask cardinality differs')
            for expert, active in zip(id_row, mask_row):
                if active not in (0.0, 1.0) or expert >= 128 or expert < -1:
                    raise GateError('C70 wave mask/ID invalid')
                if expert == -1:
                    if not skip_on or key[1] >= 25 or active != 0.0:
                        raise GateError('C70 sentinel outside parked CPU pair')
                    sentinels += 1
                elif active == 1.0 and expert < 0:
                    raise GateError('C70 active expert missing')
    if bool(sentinels) != skip_on or len(core) != 250 * len(c7.CORE):
        raise GateError('C70 sentinel/core coverage changed')
    with (root / 'byte_checks.tsv').open(newline='') as source:
        checks = list(csv.DictReader(source, delimiter='\t'))
    if not checks or any(row['status'] != 'EQUAL' for row in checks):
        raise GateError('C70 byte/lifetime witness failure')
    return {'core': core, 'logits': logits, 'masks': masks,
            'coverage': coverage, 'sentinels': sentinels,
            'byte_witness_rows': len(checks)}


def compare(off_root, on_root):
    off = inspect(off_root, skip_on=False)
    on = inspect(on_root, skip_on=True)
    if off['core'].keys() != on['core'].keys() or off['masks'].keys() != on['masks'].keys():
        raise GateError('C70 core/wave state keys changed')
    mismatch = []
    for key in sorted(off['core']):
        if off['core'][key] != on['core'][key]:
            a, b = off['core'][key], on['core'][key]
            first = next(i for i in range(0, len(a), 4) if a[i:i+4] != b[i:i+4])
            mismatch.append({'phase': key[0], 'layer': key[1],
                             'stage': key[2], 'first_value_index': first // 4})
    for key in sorted(off['masks']):
        if off['masks'][key] != on['masks'][key]:
            mismatch.append({'phase': key[0], 'layer': key[1], 'stage': 'wave_mask'})
    for phase in c7.LOGIT_PHASES:
        if off['logits'][phase] != on['logits'][phase]:
            a, b = off['logits'][phase], on['logits'][phase]
            first = next(i for i in range(0, len(a), 4) if a[i:i+4] != b[i:i+4])
            mismatch.append({'phase': phase, 'stage': 'full_logits',
                             'first_value_index': first // 4})
    return {'schema': 'c70-full-boundary-v1',
            'status': 'SAME_PROFILE_BITWISE_PASS' if not mismatch else 'FAIL_SAME_PROFILE_FIDELITY',
            'numeric_states': 250, 'masked_states': 2,
            'core_stage_comparisons': len(off['core']), 'full_logits': len(c7.LOGIT_PHASES),
            'off': {**off['coverage'], 'sentinels': off['sentinels'],
                    'byte_witness_rows': off['byte_witness_rows']},
            'on': {**on['coverage'], 'sentinels': on['sentinels'],
                   'byte_witness_rows': on['byte_witness_rows']},
            'mismatch': mismatch,
            'claim_limit': 'same-profile active states only; canonical reference and timing not included'}
