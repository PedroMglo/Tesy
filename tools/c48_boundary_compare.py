#!/usr/bin/env python3
"""Compare C48 CPU parked-pair skip against same-binary OFF and fresh ON."""

import csv
import json
import math
from pathlib import Path
import struct

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c7_boundary_gate as c7


ROOT = Path('results/c48-skip-boundary-20260928T0954Z')
RUNS = ('c48-g2-off01', 'c48-g2-on01', 'c48-g2-on02')


def rows(path, header):
    with path.open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != header:
            raise GateError(f'C48 index header: {path}')
        return list(reader)


def check_capture(path, sentinel):
    if (path/'phases.txt').read_text().splitlines() != list(c7.PHASES) or \
       rows(path/'masked.tsv', list(c7.MASKED[0])) != c7.MASKED:
        raise GateError('C48 phase/masked schema invalid')
    index = rows(path/'index.tsv', c7.INDEX_FIELDS)
    expected = {(phase, layer) for phase in c7.PHASES for layer in range(36)
                if not (layer == 35 and phase in ('prefill0', 'prefill128'))}
    core = {}
    files = set()
    sentinel_values = 0
    for row in index:
        phase, layer, stage = row['phase'], int(row['layer']), row['name']
        if (phase, layer) not in expected or stage not in c7.CORE | c7.OPTIONAL:
            raise GateError('C48 extra capture state')
        ne = tuple(int(x) for x in row['ne'].split(','))
        nb = tuple(int(x) for x in row['nb'].split(','))
        size = int(row['bytes'])
        dtype = row['type']
        chunk, first_abs, tokens = (int(row[key]) for key in ('chunk', 'first_abs', 'state_tokens'))
        if (chunk, first_abs, tokens) != c7.state_metadata(phase, layer) or \
           len(ne) != 4 or len(nb) != 4 or any(x <= 0 for x in ne+nb) or \
           nb[0] != 4 or dtype not in ('f32', 'i32') or \
           size != 4+sum((ne[i]-1)*nb[i] for i in range(4)):
            raise GateError('C48 capture metadata invalid')
        if stage in c7.CORE:
            key = (phase, layer, stage)
            if key in core:
                raise GateError('C48 duplicate core state')
            core[key] = row
            target = (2880, tokens, 1, 1) if stage in ('attn_post_norm', 'ffn_moe_out') else \
                     (128, tokens, 1, 1) if stage in ('ffn_moe_logits', 'ffn_moe_probs') else \
                     (4, tokens, 1, 1) if stage == 'ffn_moe_topk' else (1, 4, tokens, 1)
            if ne != target or dtype != ('i32' if stage == 'ffn_moe_topk' else 'f32'):
                raise GateError('C48 core shape/dtype invalid')
        file = row['file']
        if file in files or '/' in file or not file.endswith('.bin'):
            raise GateError('C48 duplicate/invalid payload path')
        files.add(file)
        payload = (path/file).read_bytes()
        if len(payload) != size:
            raise GateError('C48 payload byte count invalid')
        for i3 in range(ne[3]):
            for i2 in range(ne[2]):
                for i1 in range(ne[1]):
                    for i0 in range(ne[0]):
                        offset = i0*nb[0]+i1*nb[1]+i2*nb[2]+i3*nb[3]
                        if dtype == 'f32':
                            if not math.isfinite(struct.unpack_from('<f', payload, offset)[0]):
                                raise GateError('C48 nonfinite payload')
                        else:
                            value = struct.unpack_from('<i', payload, offset)[0]
                            if value < 0:
                                if not (sentinel and stage == 'ffn_moe_wave_ids' and value == -1):
                                    raise GateError('C48 invalid negative ID')
                                sentinel_values += 1
    expected_core = {(phase, layer, stage) for phase, layer in expected for stage in c7.CORE}
    if set(core) != expected_core or bool(sentinel_values) != sentinel:
        raise GateError('C48 missing core state or sentinel contract')
    control = {'index.tsv', 'masked.tsv', 'byte_checks.tsv', 'route_prestate.tsv',
               'phases.txt', 'stages.txt'} | {p+'.logits.f32' for p in c7.LOGIT_PHASES}
    actual = {item.name for item in path.iterdir() if item.is_file()}
    if actual != control | files:
        raise GateError('C48 unindexed/missing capture file')
    checked = rows(path/'byte_checks.tsv', ['phase','layer','wave','logical','slot',
                                             'generation','tensor','bytes','status'])
    witness = {(int(row['layer']), int(row['tensor'])) for row in checked if row['status'] == 'EQUAL'}
    if not all((layer, kind) in witness for layer in (0, 25, 29, 35) for kind in range(6)):
        raise GateError('C48 active expert byte/lifetime witnesses incomplete')
    logits = {phase: c7.f32((path/(phase+'.logits.f32')).read_bytes(), c7.VOCAB)
              for phase in c7.LOGIT_PHASES}
    return core, logits, {'numeric_states': len(expected), 'core_rows': len(core),
                          'sentinel_values': sentinel_values,
                          'index_sha256': sha256(path/'index.tsv'),
                          'byte_witness_rows': len(checked)}


def main():
    out = ROOT/'boundary-summary.json'
    if out.exists():
        raise GateError('C48 boundary comparison no-replace')
    modes = (False, True, True)
    captured = []
    for run_id, sentinel in zip(RUNS, modes):
        raw = ROOT/'raw'/f'{run_id}.json'
        manifest = strict_json(raw.read_text())
        if manifest['run_id'] != run_id or manifest['returncode'] != 0 or \
           manifest['stop_reason'] is not None or not manifest['mapped_libraries_match_ldd'] or \
           manifest['artifact_identity']['stat_at_launch'] != manifest['artifact_identity']['stat_at_end']:
            raise GateError(f'C48 bounded provenance failed: {run_id}')
        for suffix, digest in manifest['output_sha256'].items():
            if sha256(Path(str(ROOT/'raw'/run_id)+suffix)) != digest:
                raise GateError(f'C48 raw hash mismatch: {run_id}{suffix}')
        cap = ROOT/'raw'/f'{run_id}.capture'
        core, logits, coverage = check_capture(cap, sentinel)
        captured.append((core, logits, coverage))
    first_core, first_logits, _ = captured[0]
    for arm, (core, logits, _) in enumerate(captured[1:], start=1):
        for key, row in first_core.items():
            other = core[key]
            if any(row[field] != other[field] for field in ('type', 'ne', 'nb', 'bytes')) or \
               (ROOT/'raw'/f'{RUNS[0]}.capture'/row['file']).read_bytes() != \
               (ROOT/'raw'/f'{RUNS[arm]}.capture'/other['file']).read_bytes():
                raise GateError(f'C48 same-profile core mismatch at {key} arm {arm}')
        for phase in c7.LOGIT_PHASES:
            if logits[phase] != first_logits[phase]:
                raise GateError(f'C48 same-profile complete logits mismatch at {phase} arm {arm}')
    result = {'schema': 'c48-boundary-summary-v1', 'status': 'SAME_PROFILE_BITWISE_PASS',
              'run_ids': list(RUNS), 'coverage': [item[2] for item in captured],
              'core_state_comparisons': len(first_core)*2,
              'complete_logit_vectors_compared': len(c7.LOGIT_PHASES)*2,
              'logit_width_f32': c7.VOCAB,
              'masked_states_per_arm': 2,
              'numeric_profile': 'C48 CPU parked-pair skip ON; OFF same-binary control',
              'canonical_layers': 'NOT_RUN',
              'limits': ['bitwise OFF/ON/fresh ON on selected states and logits only',
                         'canonical resident layer references and timing promotion require separate gate']}
    with out.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'core_comparisons': result['core_state_comparisons']}))


if __name__ == '__main__':
    main()
