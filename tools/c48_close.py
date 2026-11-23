#!/usr/bin/env python3
"""Preserve C48 OFF/ON same-profile failure and its unused third arm."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256
import c48_boundary_compare as compare


ROOT = compare.ROOT
INDEX = Path('results/120b-program-index.json')


def read(path):
    return strict_json(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def main():
    names = ('decision.json', 'resource-summary.json', 'manifest.json', 'boundary-summary.json')
    if any((ROOT/name).exists() for name in names):
        raise GateError('C48 closure no-replace')
    off_id, on_id, repeat_id = compare.RUNS
    off, on = (read(ROOT/f'{rid}-receipt.json') for rid in (off_id, on_id))
    raw_off, raw_on = (read(ROOT/'raw'/f'{rid}.json') for rid in (off_id, on_id))
    pair = read(ROOT/'pair-gate.json')
    if off['status'] != on['status'] or off['status'] != 'PASS_CAPTURE_SCOPE' or \
       pair['status'] != 'FAIL_SAME_PROFILE_FIDELITY' or \
       (ROOT/f'{repeat_id}-receipt.json').exists() or \
       (ROOT/'raw'/f'{repeat_id}.json').exists():
        raise GateError('C48 expected OFF/ON failure or repeat state differs')
    for raw in (raw_off, raw_on):
        cg = raw['cgroup_end']
        if raw['returncode'] != 0 or raw['stop_reason'] is not None or \
           cg['swap_current'] or cg['events']['oom'] or cg['events']['oom_kill']:
            raise GateError('C48 unexpected process/resource failure')
    a, al, ac = compare.check_capture(ROOT/'raw'/f'{off_id}.capture', False)
    b, bl, bc = compare.check_capture(ROOT/'raw'/f'{on_id}.capture', True)
    differences = []
    for key, row in a.items():
        left = (ROOT/'raw'/f'{off_id}.capture'/row['file']).read_bytes()
        right = (ROOT/'raw'/f'{on_id}.capture'/b[key]['file']).read_bytes()
        if left != right:
            differences.append(key)
    if not differences or differences[0] != ('prefill0', 0, 'ffn_moe_out'):
        raise GateError('C48 observed first divergence differs')
    first = differences[0]
    first_a = (ROOT/'raw'/f'{off_id}.capture'/a[first]['file']).read_bytes()
    first_b = (ROOT/'raw'/f'{on_id}.capture'/b[first]['file']).read_bytes()
    offset = next(i for i in range(0, len(first_a), 4)
                  if first_a[i:i+4] != first_b[i:i+4])
    first_value = {'phase': first[0], 'layer': first[1], 'stage': first[2],
                   'flat_f32_index': offset//4, 'token_in_chunk': (offset//4)//2880,
                   'feature': (offset//4)%2880,
                   'off_f32': struct.unpack_from('<f', first_a, offset)[0],
                   'on_f32': struct.unpack_from('<f', first_b, offset)[0]}
    logits_equal = {phase: al[phase] == bl[phase] for phase in compare.c7.LOGIT_PHASES}
    if any(logits_equal.values()):
        raise GateError('C48 complete-logit mismatch coverage differs')
    idle_total = sum(read(path)['duration_s'] for path in Path('results').glob('c*-*/**/*-idle.json'))
    used = program_physical_consumed() + idle_total + 2400
    protocol = read(ROOT/'protocol.json')
    decision = {
        'schema': 'c48-decision-v1', 'status': 'FAIL_SAME_PROFILE_FIDELITY',
        'measurement_commit': off['measurement_commit'],
        'backend_commit': protocol['backend_commit'],
        'run_order': [off_id, on_id],
        'old_failures_preserved': ['C47 first ON runtime assertion',
                                   'C43/C44 profiler prelaunch FAILs',
                                   'C9-C17 CPU95 protocol thermal FAILs'],
        'off': {'run_id': off_id, 'status': 'PASS_CAPTURE_SCOPE', 'elapsed_s': off['elapsed_s']},
        'on': {'run_id': on_id, 'status': 'PASS_CAPTURE_SCOPE_BUT_PAIR_FAIL',
               'elapsed_s': on['elapsed_s'], 'sentinel_values': bc['sentinel_values']},
        'on_fresh_repeat': {'run_id': repeat_id, 'status': 'NOT_RUN_AFTER_PAIR_FAIL'},
        'first_observed_difference': first_value,
        'core_mismatch_rows': len(differences),
        'complete_logits_equal': logits_equal,
        'same_pin_canonical_reference': 'NOT_RUN', 'timing': 'NOT_RUN',
        'physical_budget_consumed_s': used,
        'physical_budget_remaining_s': 16*3600-used,
        'next_action': 'Pivot to the exact-prefix/session M3 gate: define a new contemporary OFF/ON server pair with frozen session inputs and endpoint timings; do not reuse C48 for performance',
        'M3': 'PARTIAL', 'M4': 'NOT_RUN', 'default_changed': False,
        'closed_utc': datetime.now(timezone.utc).isoformat(),
    }
    resources = {
        'schema': 'c48-resource-summary-v1',
        'status': 'BOTH_ARMS_RESOURCE_PASS',
        'off_maxima': off['maxima'], 'on_maxima': on['maxima'],
        'off_cgroup_end': raw_off['cgroup_end'], 'on_cgroup_end': raw_on['cgroup_end'],
        'off_start': off['idle']['end'], 'on_start': on['idle']['end'],
        'limit': 'numeric mismatch stops C48; capture elapsed times are not performance measurements',
    }
    boundary = {
        'schema': 'c48-boundary-summary-v1', 'status': 'FAIL_SAME_PROFILE_FIDELITY',
        'first_observed_difference': first_value,
        'core_mismatch_rows': len(differences),
        'core_mismatch_by_stage': dict(Counter(key[2] for key in differences)),
        'numeric_states_per_arm': ac['numeric_states'],
        'core_rows_per_arm': len(a), 'masked_states_per_arm': 2,
        'complete_logits_equal': logits_equal,
        'sentinel_values_off': ac['sentinel_values'],
        'sentinel_values_on': bc['sentinel_values'],
        'fresh_on_repeat': 'NOT_RUN', 'canonical_reference': 'NOT_RUN',
    }
    raw_paths = [ROOT/'raw'/f'{rid}{suffix}' for rid in (off_id, on_id)
                 for suffix in ('.json', '.stdout', '.stderr', '.samples.jsonl')]
    manifest = {'schema': 'c48-manifest-v1',
                'measurement_commit': off['measurement_commit'],
                'compact_sha256': {name: sha256(ROOT/name) for name in
                                   ('protocol.json', 'preflight.json',
                                    'pair-gate.json', f'{off_id}-receipt.json',
                                    f'{on_id}-receipt.json')},
                'raw_sha256': {str(path): sha256(path) for path in raw_paths},
                'capture_index_sha256': {rid: sha256(ROOT/'raw'/f'{rid}.capture/index.tsv')
                                         for rid in (off_id, on_id)}}
    for name, obj in zip(names, (decision, resources, manifest, boundary)):
        write_new(ROOT/name, obj)
    with (ROOT/'LEDGER.md').open('a') as out:
        out.write(f'\n- OFF {off_id}: capture/resource PASS, {off["elapsed_s"]:.3f} s. ON {on_id}: capture/resource PASS, {on["elapsed_s"]:.3f} s.\n')
        out.write(f'- Pair FAIL: first difference {first_value}; {len(differences)}/1500 core rows and all five full logits differ. Fresh ON, canonical layers and timing NOT_RUN.\n')
        out.write('- Next: distinct exact-prefix/session gate for M3. C47 and C48 failures retained.\n')
    index = read(INDEX)
    index['units'].append({'identity': 'c48', 'root': str(ROOT),
                           'status': decision['status'],
                           'first_observed_difference': first_value})
    index['next_action'] = decision['next_action']
    index['updated_utc'] = decision['closed_utc']
    temp = INDEX.with_suffix('.json.tmp')
    with temp.open('x') as out:
        json.dump(index, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')
    temp.replace(INDEX)
    print(json.dumps({'status': decision['status'],
                      'first': first_value, 'core_mismatch_rows': len(differences),
                      'physical_budget_remaining_s': decision['physical_budget_remaining_s']}))


if __name__ == '__main__':
    main()
