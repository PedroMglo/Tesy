#!/usr/bin/env python3
"""Revalidate and close the four-arm C22 exploratory prefix screen."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from c22_prefix_pairs import SPEC, frozen, validate_arm
from c8_observer_runner import program_physical_consumed
from c9_server_admission import digest
from run_bounded import sha256


def write_x(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def gain(control, candidate):
    if control <= 0:
        raise GateError('paired control time nonpositive')
    return 100 * (control - candidate) / control


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    policy = strict_json((root / 'protocol.json').read_text())
    if policy['schema'] != 'c22-prefix-pairs-protocol-v1':
        raise GateError('wrong frozen screen protocol')
    rows = []
    for spec in SPEC:
        run_id, arm, phase, order = spec
        protocol, config, _, _ = frozen(root, spec)
        protocol_path = root / 'protocols' / f'{run_id}.json'
        if protocol != strict_json(protocol_path.read_text()) or \
                policy['per_run_protocol_sha256'][run_id] != sha256(protocol_path):
            raise GateError('per-run protocol/source changed: ' + run_id)
        receipt = strict_json((root / f'{run_id}-receipt.json').read_text())
        idle = strict_json((root / f'{run_id}-idle.json').read_text())
        raw_path = root / 'raw' / f'{run_id}.json'
        raw = strict_json(raw_path.read_text())
        if receipt['status'] != 'PASS_ARM' or receipt['raw_sha256'] != sha256(raw_path) or \
                idle != receipt['idle'] or idle['status'] != 'PASS' or \
                idle['qualifying_duration_s'] < 300 or idle['max_gap_qualifying_s'] > 1 or \
                idle['match_tolerance_c'] != [5, 5, 3] or idle['max_start_c'] != [50, 50, 45]:
            raise GateError('arm raw/admission invalid: ' + run_id)
        status, maxima, cpu, server_gate, common, ids = validate_arm(
            root, spec, protocol, config, raw)
        if status != 'PASS_ARM' or maxima != receipt['maxima'] or \
                cpu != receipt['cpu_diagnostics'] or server_gate != receipt['server_gate'] or \
                common != receipt['actual_common_prefix_ids'] or \
                {key: digest(value) for key, value in ids.items()} != receipt['token_id_sha256']:
            raise GateError('arm compact differs from raw: ' + run_id)
        times = [result['ended_s'] - result['started_s'] for result in raw['results']]
        if len(times) != 2 or any(t <= 0 for t in times) or \
                len(receipt['results']) != 2 or \
                any(raw_result['timings'] != compact['timings'] or
                    raw_result['usage'] != compact['usage'] for raw_result, compact in
                    zip(raw['results'], receipt['results'])):
            raise GateError('completion-fenced outputs invalid: ' + run_id)
        rows.append({'run_id': run_id, 'arm': arm, 'pair': phase, 'order': order,
                     'measurement_commit': receipt['measurement_commit'],
                     'status': status, 'raw_sha256': sha256(raw_path),
                     'first_request_s': times[0], 'second_request_s': times[1],
                     'cache_n': [r['timings']['cache_n'] for r in receipt['results']],
                     'message_sha256': [r['message_sha256'] for r in receipt['results']],
                     'token_id_sha256': receipt['token_id_sha256'],
                     'actual_common_prefix_ids': common,
                     'maxima': maxima, 'cpu_diagnostics': cpu,
                     'idle_duration_s': idle['duration_s'],
                     'start_temperatures_c': {'cpu': idle['end']['cpu_c'],
                                              'gpu': idle['end']['gpu']['temperature_c'],
                                              'nvme': idle['end']['nvme_c']}})
    if len({tuple(x['message_sha256']) for x in rows}) != 1 or \
            len({json.dumps(x['token_id_sha256'], sort_keys=True) for x in rows}) != 1:
        raise GateError('outputs or token IDs differ across paired arms')
    series = root / 'thermal-series.jsonl'
    idle_rows = [strict_json(line) for line in series.read_text().splitlines()]
    if len(idle_rows) != sum(strict_json((root / f'{x[0]}-idle.json').read_text())['sample_count']
                             for x in SPEC):
        raise GateError('idle series count incomplete')
    pairs = []
    for phase in ('P1', 'P2'):
        pair = [row for row in rows if row['pair'] == phase]
        if len(pair) != 2 or {x['arm'] for x in pair} != {'off', 'on'}:
            raise GateError('missing OFF/ON pair')
        off = next(x for x in pair if x['arm'] == 'off')
        on = next(x for x in pair if x['arm'] == 'on')
        pairs.append({'pair': phase, 'order': [x['arm'] for x in pair],
                      'off_run_id': off['run_id'], 'on_run_id': on['run_id'],
                      'off_first_s': off['first_request_s'], 'on_first_s': on['first_request_s'],
                      'off_second_s': off['second_request_s'], 'on_second_s': on['second_request_s'],
                      'gain_first_pct': gain(off['first_request_s'], on['first_request_s']),
                      'gain_second_pct': gain(off['second_request_s'], on['second_request_s'])})
    screen = policy['screen_policy']
    go = (median(p['gain_second_pct'] for p in pairs) >= screen['median_second_gain_pct_min'] and
          all(p['gain_second_pct'] > screen['each_second_gain_pct_min_exclusive'] for p in pairs) and
          median(p['gain_first_pct'] for p in pairs) >= screen['median_first_cold_gain_pct_min'] and
          all((x['cache_n'][1] == 0 if x['arm'] == 'off' else
               screen['cache_on_min_ids'] <= x['cache_n'][1] <= x['actual_common_prefix_ids'])
              for x in rows))
    with (root / 'runs.jsonl').open('a') as out:
        last = rows[-1]
        out.write(json.dumps({key: last[key] for key in
            ('run_id','arm','pair','order','status','measurement_commit','raw_sha256',
             'first_request_s','second_request_s','cache_n')}, sort_keys=True, allow_nan=False)+'\n')
    # The first three rows were recorded after their respective measurement commits.
    recorded = [strict_json(line) for line in (root / 'runs.jsonl').read_text().splitlines()]
    if [x['run_id'] for x in recorded] != [x[0] for x in SPEC]:
        raise GateError('run index order invalid')
    timing = {'schema': 'c22-timing-pairs-v1', 'status': 'SCREEN_GO' if go else 'SCREEN_NO_GO',
              'metric': policy['metric'], 'formula': policy['paired_gain_formula'],
              'pairs': pairs, 'median_gain_first_pct': median(p['gain_first_pct'] for p in pairs),
              'median_gain_second_pct': median(p['gain_second_pct'] for p in pairs),
              'old_times_used': False, 'confirmation_pairs_included': False}
    resource = {'schema': 'c22-resource-summary-v1', 'status': 'ALL_FOUR_ARMS_QUALIFIED',
                'runs': rows, 'idle_series_sha256': sha256(series),
                'ambient_temperature': 'UNKNOWN',
                'thermal_limit_note': 'AMD direct hardware throttle flag unavailable; ACPI Processor cooling and effective clocks captured'}
    previous_idle_s = 394.4515725659985
    for prior in ('c17-thermal-recovery-20260927T1656Z',
                  'c18-cpu100-retest-20260927T1756Z',
                  'c19-prefix-20260927T1842Z',
                  'c20-prefix-pairs-20260927T1857Z',
                  'c21-prefix-pairs-20260927T1927Z'):
        previous_idle_s += sum(strict_json(path.read_text())['duration_s'] for path in
                               Path('results', prior).glob('*-idle.json'))
    current_idle_s = sum(x['idle_duration_s'] for x in rows)
    server_s = program_physical_consumed()
    used_s = previous_idle_s + current_idle_s + server_s
    decision = {'schema': 'c22-decision-v1',
                'status': 'SCREEN_GO_CONFIRMATION_REQUIRED' if go else 'NO_GO_PREFIX_SCREEN',
                'gates': {'model_identity': 'PASS', 'four_arm_resources': 'PASS',
                          'four_arm_outputs_and_cache': 'PASS',
                          'paired_screen': 'PASS' if go else 'NO_GO',
                          'same_profile_full_logits': 'NOT_RUN',
                          'M3': 'PARTIAL_PREFIX_MECHANISM_ONLY', 'M4': 'NOT_RUN',
                          'C15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED'},
                'pairs': pairs, 'runs': [x['run_id'] for x in rows],
                'claims': ['Synthetic 513/641-ID P12 server prefix-reuse screen only',
                           'Returned message equality is not full-logit or sampling equality',
                           'Two pairs do not establish tail latency or sustained session utility'],
                'old_fails_preserved': 'C9/C10b/C13/C14/C17 CPU95 failures, C20 incomplete pair and C21 prelaunch failure unchanged',
                'budget': {'physical_limit_s':57600,'raw_server_cumulative_s':server_s,
                           'prior_idle_s':previous_idle_s,'c22_idle_s':current_idle_s,
                           'accounted_physical_used_s':used_s,'remaining_s':57600-used_s},
                'next_action': ('C23: three new OFF/ON prefix-confirmation pairs in frozen alternating order and the same profile/guards; no C22 times in confirmatory median.'
                                if go else 'Pivot to next bounded M3 hypothesis; do not promote prefix speed claim.'),
                'default_changed':False,'closed_utc':datetime.now(timezone.utc).isoformat()}
    write_x(root / 'timing-pairs.json', timing)
    write_x(root / 'resource-summary.json', resource)
    write_x(root / 'decision.json', decision)
    write_x(root / 'manifest.json', {'schema':'c22-results-manifest-v1',
        'compact_sha256':{name:sha256(root/name) for name in
            ('protocol.json','preflight.json','runs.jsonl','timing-pairs.json',
             'resource-summary.json','decision.json','environment-intervention.json')},
        'raw_server_sha256':{x['run_id']:x['raw_sha256'] for x in rows},
        'raw_idle_series_sha256':sha256(series), 'default_changed':False})
    print(json.dumps({'status':decision['status'],
                      'median_gain_second_pct':timing['median_gain_second_pct'],
                      'accounted_physical_used_s':used_s},allow_nan=False))


if __name__ == '__main__':
    main()
