#!/usr/bin/env python3
"""Bounded footprint of the C76b captured router IDs; no cache-hit inference."""

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from c2_gate import GateError, strict_json

ROOT = Path('results/c76b-session-wave-boundary-20260928T1918Z')
OUT = Path('results/c83-captured-router-footprint-20260928T1954Z')
LABELS = ('prefill0', 'prefill128', 'prefill_final',
          'decode0', 'decode1', 'decode7', 'decode31')
EXPERT_BYTES = 13_219_200


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def checked_rows(index, capture, manifest):
    with index.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != ['phase', 'layer', 'chunk', 'first_abs',
                                 'state_tokens', 'name', 'type', 'ne', 'nb',
                                 'bytes', 'file']:
            raise GateError('C76b index schema changed')
        rows = list(reader)
    selected = {}
    for row in rows:
        if row['name'] != 'ffn_moe_topk':
            continue
        label = row['phase']
        layer = int(row['layer'])
        key = (label, layer)
        if label not in LABELS or not 0 <= layer < 36 or key in selected:
            raise GateError('invalid or duplicate router state')
        if layer == 35 and label in ('prefill0', 'prefill128'):
            raise GateError('masked router state has numeric payload')
        count = (1 if layer == 35 and label == 'prefill_final' else
                 {'prefill0': 32, 'prefill128': 32, 'prefill_final': 29}.get(label, 1))
        first = {'prefill0': 0, 'prefill128': 128, 'prefill_final': 160,
                 'decode0': 189, 'decode1': 190, 'decode7': 196, 'decode31': 220}[label]
        if layer == 35 and label == 'prefill_final':
            first = 188
        if row['type'] != 'i32' or row['ne'] != f'4,{count},1,1' or \
           int(row['state_tokens']) != count or int(row['first_abs']) != first:
            raise GateError('router shape/position changed')
        nb = [int(x) for x in row['nb'].split(',')]
        if len(nb) != 4 or nb[0] != 4 or nb[1] < 16 or nb[1] % 4 or \
           nb[2] < count * nb[1] or nb[3] < nb[2]:
            raise GateError('router stride invalid')
        expected_bytes = (count - 1) * nb[1] + 16
        if int(row['bytes']) != expected_bytes:
            raise GateError('router byte count invalid')
        filename = row['file']
        if Path(filename).name != filename or not filename.endswith('.bin'):
            raise GateError('router path invalid')
        path = capture / filename
        relative = str(path.relative_to(capture.parent.parent))
        expected = manifest['raw_sha256'].get(relative)
        if not expected or path.stat().st_size != expected_bytes or \
           expected['bytes'] != expected_bytes or sha(path) != expected['sha256']:
            raise GateError('router payload/manifest mismatch')
        data = path.read_bytes()
        tokens = []
        for t in range(count):
            ids = struct.unpack_from('<4i', data, t * nb[1])
            if any(not 0 <= expert < 128 for expert in ids) or len(set(ids)) != 4:
                raise GateError('invalid router IDs')
            tokens.append(ids)
        selected[key] = tokens
    expected = {(label, layer) for label in LABELS for layer in range(36)
                if not (layer == 35 and label in ('prefill0', 'prefill128'))}
    if set(selected) != expected:
        raise GateError(f'router states incomplete: {len(selected)}/{len(expected)}')
    return selected


def summarize(selected):
    states = {}
    for label in LABELS:
        keys = {(layer, expert) for (phase, layer), tokens in selected.items()
                if phase == label for ids in tokens for expert in ids}
        states[label] = {'selected_pairs': sum(len(ids) for (phase, _), tokens in selected.items()
                                             if phase == label for ids in tokens),
                         'distinct_layer_experts': len(keys),
                         'distinct_payload_bytes': len(keys) * EXPERT_BYTES,
                         'distinct_payload_mib': len(keys) * EXPERT_BYTES / 2**20}
    adjacency = {}
    for earlier, later in (('decode0', 'decode1'), ('decode1', 'decode7'),
                           ('decode7', 'decode31')):
        a = {(layer, expert) for (phase, layer), tokens in selected.items()
             if phase == earlier for ids in tokens for expert in ids}
        b = {(layer, expert) for (phase, layer), tokens in selected.items()
             if phase == later for ids in tokens for expert in ids}
        adjacency[f'{earlier}_to_{later}'] = {'common_keys': len(a & b),
                                             'later_keys_not_in_earlier': len(b - a),
                                             'sample_gap_decode_steps': int(later[6:]) - int(earlier[6:])}
    union = {(layer, expert) for (phase, layer), tokens in selected.items()
             if phase.startswith('decode') for ids in tokens for expert in ids}
    return {'schema': 'c83-captured-router-footprint-v1',
            'evidence_class': 'INFERIDO_FROM_HASH_VERIFIED_CAPTURE',
            'expert_payload_bytes': EXPERT_BYTES,
            'states': states,
            'decode_checkpoint_union': {'distinct_layer_experts': len(union),
                                        'distinct_payload_mib': len(union) * EXPERT_BYTES / 2**20},
            'checkpoint_overlap': adjacency,
            'limitations': [
                'Only four decode checkpoints, not a continuous decode trace; intervening tokens and evictions unknown.',
                'Distinct payload capacity is not the required cache size or a simulated hit rate.',
                'Existing per-layer streamed slots already retain some experts; overlap is not incremental L2 benefit.',
                'No NVMe physical traffic, exposed wait or causal latency saving is measured.',
                'The n_ctx4096 preload-OFF probe is not the n_ctx8192 preload-ON server session.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    root = args.root
    manifest = strict_json((root / 'manifest.json').read_text())
    summary = strict_json((root / 'boundary-summary.json').read_text())
    if manifest['backend_commit'] != '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5' or \
       manifest['boundary_summary_sha256'] != sha(root / 'boundary-summary.json') or \
       summary['comparison']['mismatch'] or summary['comparison']['numeric_states'] != 250:
        raise GateError('C76b source/fidelity claim changed')
    capture = root / 'raw/c76b-p12-session-wave-on01.capture'
    index = capture / 'index.tsv'
    listed = manifest['raw_sha256'].get(str(index.relative_to(root)))
    if not listed or listed['sha256'] != sha(index) or listed['bytes'] != index.stat().st_size:
        raise GateError('C76b index/manifest mismatch')
    selected = checked_rows(index, capture, manifest)
    result = summarize(selected)
    result['source_sha256'] = {'manifest': sha(root / 'manifest.json'),
                               'index': sha(index),
                               'boundary_summary': sha(root / 'boundary-summary.json')}
    result['captured_numeric_router_states'] = len(selected)
    result['parent_status'] = strict_json((root / 'decision.json').read_text())['status']
    output = args.output / 'footprint.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': 'PASS_MODEL_FREE', 'output': str(output),
                      'decode_checkpoint_union': result['decode_checkpoint_union']}))


if __name__ == '__main__':
    main()
