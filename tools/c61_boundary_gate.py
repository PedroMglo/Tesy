#!/usr/bin/env python3
"""Frozen layer-0/prefill-0 C57 wave-skip diagnostic; no timing claim."""

import argparse
import collections
import csv
import hashlib
import math
from pathlib import Path
import re
import struct

from c2_gate import GateError
import c7_boundary_gate as c7

CORE = frozenset(c7.CORE)
WAVE = frozenset({'ffn_moe_wave_ids', 'ffn_moe_wave_mask'})
STAGES = CORE | WAVE
EXPECTED_COUNTS = {**{name: 1 for name in CORE},
                   'ffn_moe_wave_ids': 10, 'ffn_moe_wave_mask': 10}
CONTROL = {'index.tsv', 'masked.tsv', 'byte_checks.tsv', 'route_prestate.tsv',
           'phases.txt', 'stages.txt'} | {p + '.logits.f32' for p in c7.LOGIT_PHASES}


def rows(path, fields):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != fields:
            raise GateError(f'index header invalid: {path}')
        return list(reader)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root, skip_on):
    if (root/'phases.txt').read_text().splitlines() != list(c7.PHASES):
        raise GateError('phase/call plan changed')
    if rows(root/'masked.tsv', list(c7.MASKED[0])) != c7.MASKED:
        raise GateError('masked graph states changed')
    index = rows(root/'index.tsv', c7.INDEX_FIELDS)
    counts = collections.Counter()
    indexed = set()
    core = {}
    sentinels = 0
    for row in index:
        phase, layer, stage = row['phase'], int(row['layer']), row['name']
        if (phase, layer) != ('prefill0', 0) or stage not in STAGES:
            raise GateError('extra/out-of-scope tensor')
        counts[stage] += 1
        if counts[stage] > EXPECTED_COUNTS[stage]:
            raise GateError('duplicate/extra stage')
        chunk, first, tokens = (int(row[k]) for k in ('chunk','first_abs','state_tokens'))
        if (chunk, first, tokens) != (0, 0, 32):
            raise GateError('chunk/absolute position/width changed')
        ne = tuple(int(x) for x in row['ne'].split(','))
        nb = tuple(int(x) for x in row['nb'].split(','))
        dtype = row['type']
        if stage in ('attn_post_norm', 'ffn_moe_out'):
            target, target_dtype = (2880,32,1,1), 'f32'
        elif stage in ('ffn_moe_logits', 'ffn_moe_probs'):
            target, target_dtype = (128,32,1,1), 'f32'
        elif stage in ('ffn_moe_topk', 'ffn_moe_wave_ids'):
            target, target_dtype = (4,32,1,1), 'i32'
        else:
            target, target_dtype = (1,4,32,1), 'f32'
        if len(ne) != 4 or ne != target or dtype != target_dtype or len(nb) != 4 or \
           nb[0] != 4 or any(x <= 0 for x in nb):
            raise GateError('stage dtype/shape/stride invalid')
        # Topk uses a padded row stride; wave tensors are contiguous.
        if stage == 'ffn_moe_topk':
            expected_nb = (4,512,16384,16384)
        else:
            expected_nb = tuple(4*math.prod(ne[:i]) for i in range(4))
        if nb != expected_nb:
            raise GateError('stage stride differs from frozen graph')
        size = 4 + sum((ne[i]-1)*nb[i] for i in range(4))
        if int(row['bytes']) != size:
            raise GateError('declared byte count invalid')
        file = row['file']
        if not re.fullmatch(rf'prefill0_0_{re.escape(stage)}_\d+\.bin', file) or file in indexed:
            raise GateError('duplicate/invalid payload path')
        indexed.add(file)
        payload = (root/file).read_bytes()
        if len(payload) != size:
            raise GateError('payload byte count invalid')
        for i3 in range(ne[3]):
            for i2 in range(ne[2]):
                for i1 in range(ne[1]):
                    for i0 in range(ne[0]):
                        offset = sum(i*stride for i,stride in zip((i0,i1,i2,i3),nb))
                        if dtype == 'f32':
                            value = struct.unpack_from('<f',payload,offset)[0]
                            if not math.isfinite(value):
                                raise GateError('nonfinite tensor value')
                        else:
                            value = struct.unpack_from('<i',payload,offset)[0]
                            if value < 0:
                                if not (skip_on and stage == 'ffn_moe_wave_ids' and value == -1):
                                    raise GateError('invalid negative routed ID')
                                sentinels += 1
                            elif value >= 128:
                                raise GateError('expert ID outside model')
        if stage in CORE:
            core[stage] = payload
    if counts != EXPECTED_COUNTS or bool(sentinels) != skip_on:
        raise GateError('stage multiplicity or sentinel contract invalid')
    if {p.name for p in root.iterdir() if p.is_file()} != indexed | CONTROL:
        raise GateError('missing/unindexed capture file')
    checks = rows(root/'byte_checks.tsv', ['phase','layer','wave','logical','slot',
                                            'generation','tensor','bytes','status'])
    if not checks or any(r['phase'] != 'prefill0' or r['layer'] != '0' or
                         r['status'] != 'EQUAL' for r in checks):
        raise GateError('byte/lifetime witness failed or absent')
    if {int(r['tensor']) for r in checks} != set(range(6)):
        raise GateError('byte/lifetime tensor kinds incomplete')
    rows(root/'route_prestate.tsv',['phase','layer','expert','class','slot','generation'])
    logits = {p:c7.f32((root/(p+'.logits.f32')).read_bytes(),c7.VOCAB)
              for p in c7.LOGIT_PHASES}
    return core,logits,{'index_sha256':sha(root/'index.tsv'),
                         'core_states':len(core),'wave_rows':sum(counts[s] for s in WAVE),
                         'sentinel_values':sentinels,'byte_witness_rows':len(checks),
                         'logits_sha256':{p:hashlib.sha256(v).hexdigest() for p,v in logits.items()}}


def compare(off, on):
    a,al,ac = validate(off,False)
    b,bl,bc = validate(on,True)
    mismatch = []
    for name in sorted(CORE):
        if a[name] != b[name]:
            first = next(i for i in range(0,len(a[name]),4) if a[name][i:i+4] != b[name][i:i+4])
            mismatch.append({'stage':name,'first_value_index':first//4})
    for phase in c7.LOGIT_PHASES:
        if al[phase] != bl[phase]:
            first = next(i for i in range(0,len(al[phase]),4)
                         if al[phase][i:i+4] != bl[phase][i:i+4])
            mismatch.append({'phase':phase,'first_logit_index':first//4})
    return {'schema':'c61-targeted-boundary-v1',
            'status':'SAME_PROFILE_BITWISE_PASS' if not mismatch else 'FAIL_SAME_PROFILE_FIDELITY',
            'scope':'P12 layer0 prefill0 active states and five selected complete logits',
            'off':ac,'on':bc,'mismatch':mismatch,
            'not_run':['canonical resident layer reference','remaining layers','timing']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('off',type=Path)
    parser.add_argument('on',type=Path)
    args=parser.parse_args()
    import json
    print(json.dumps(compare(args.off,args.on),sort_keys=True,allow_nan=False))


if __name__ == '__main__':
    main()
