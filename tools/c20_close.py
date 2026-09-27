#!/usr/bin/env python3
"""Close the incomplete C20 pair without promoting its lone control arm."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c20_prefix_pairs import SPEC, frozen, validate_arm
from run_bounded import sha256


def write_x(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    off_id, on_id = SPEC[0][0], SPEC[1][0]
    off = strict_json((root / f'{off_id}-receipt.json').read_text())
    on = strict_json((root / f'{on_id}-receipt.json').read_text())
    off_idle = strict_json((root / f'{off_id}-idle.json').read_text())
    on_idle = strict_json((root / f'{on_id}-idle.json').read_text())
    protocol, config, _, _ = frozen(root, SPEC[0])
    raw_path = root / 'raw' / f'{off_id}.json'
    raw = strict_json(raw_path.read_text())
    if off['status'] != 'PASS_ARM' or off_idle['status'] != 'PASS' or \
            off['raw_sha256'] != sha256(raw_path) or \
            protocol != strict_json((root / 'protocols' / f'{off_id}.json').read_text()):
        raise GateError('C20 OFF evidence does not match frozen protocol')
    status, maxima, cpu, _, common, _ = validate_arm(root, SPEC[0], protocol, config, raw)
    if status != 'PASS_ARM' or maxima != off['maxima'] or cpu != off['cpu_diagnostics'] or \
            common != off['actual_common_prefix_ids']:
        raise GateError('C20 OFF raw revalidation differs')
    if on['status'] != 'THERMAL_PREFLIGHT_BLOCKED' or on['model_runs'] != 0 or \
            on_idle['status'] != 'THERMAL_PREFLIGHT_BLOCKED' or \
            on_idle['duration_s'] < 900 or (root / 'raw' / f'{on_id}.json').exists():
        raise GateError('C20 ON was not a no-model preflight block')
    if any((root / f'{spec[0]}-receipt.json').exists() for spec in SPEC[2:]):
        raise GateError('unexpected later C20 arm')
    samples = (root / 'thermal-series.jsonl').read_text().splitlines()
    if len(samples) != off_idle['sample_count'] + on_idle['sample_count'] or \
            any(strict_json(line)['run_id'] != (off_id if i < off_idle['sample_count'] else on_id)
                for i, line in enumerate(samples)):
        raise GateError('C20 idle series incomplete or disordered')
    runs = [
        {'run_id': off_id, 'arm': 'OFF', 'status': 'PASS_ARM',
         'measurement_commit': off['measurement_commit'],
         'raw_sha256': off['raw_sha256'],
         'first_request_s': raw['results'][0]['ended_s']-raw['results'][0]['started_s'],
         'second_request_s': raw['results'][1]['ended_s']-raw['results'][1]['started_s'],
         'cpu_max_c': maxima['cpu_c'], 'start_cpu_c': off_idle['end']['cpu_c']},
        {'run_id': on_id, 'arm': 'ON', 'status': 'THERMAL_PREFLIGHT_BLOCKED',
         'measurement_commit': on['measurement_commit'], 'model_runs': 0,
         'idle_duration_s': on_idle['duration_s'],
         'start_cpu_c': on_idle['end']['cpu_c'],
         'baseline_cpu_c': on_idle['baseline']['cpu_c']},
    ]
    with (root / 'runs.jsonl').open('a') as out:
        out.write(json.dumps(runs[1], sort_keys=True, allow_nan=False)+'\n')
    write_x(root / 'timing-pairs.json', {'schema': 'c20-timing-pairs-v1',
        'status': 'INCOMPLETE_NO_PAIRED_GAIN', 'pairs': [],
        'unpaired_off_second_s': runs[0]['second_request_s'],
        'old_or_unpaired_times_used_for_gain': False})
    write_x(root / 'resource-summary.json', {'schema': 'c20-resource-summary-v1',
        'runs': runs, 'idle_series_sha256': sha256(root / 'thermal-series.jsonl'),
        'on_preflight_reason': 'C20 frozen start band CPU ±2 C/GPU ±3 C versus first OFF arm; ON was cooler',
        'gpu_nvme_ram_guards_changed': False})
    write_x(root / 'decision.json', {'schema': 'c20-decision-v1',
        'status': 'THERMAL_PREFLIGHT_BLOCKED',
        'reason': 'ON start did not match the warmer OFF baseline within the frozen 900 s admission; ON model not loaded',
        'runs': runs, 'pairs_complete': 0, 'paired_gain_pct': None,
        'C20_p2': 'NOT_RUN', 'C15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED',
        'M3': 'PARTIAL_PREFIX_MECHANISM_ONLY', 'M4': 'NOT_RUN',
        'old_fails_preserved': 'C9/C10b/C13/C14/C17 CPU95 receipts unchanged',
        'next_action': 'C21 fresh OFF/ON pairs with a new prospective matched cool-start band; do not reuse C20 OFF for gain',
        'default_changed': False, 'closed_utc': datetime.now(timezone.utc).isoformat()})
    write_x(root / 'manifest.json', {'schema': 'c20-results-manifest-v1',
        'compact_sha256': {p.name: sha256(p) for p in
            (root / 'protocol.json', root / 'preflight.json', root / 'runs.jsonl',
             root / 'timing-pairs.json', root / 'resource-summary.json', root / 'decision.json')},
        'raw_server_sha256': {off_id: off['raw_sha256']},
        'raw_idle_series_sha256': sha256(root / 'thermal-series.jsonl'),
        'default_changed': False})
    print(json.dumps({'status':'THERMAL_PREFLIGHT_BLOCKED','on_model_runs':0,'pairs':0}))


if __name__ == '__main__':
    main()
