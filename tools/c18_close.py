#!/usr/bin/env python3
"""Close the four-arm CPU100 retest from immutable raw and frozen protocols."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median

from c18_cpu_telemetry import summarize_samples
from c18_thermal_retest import SPEC, frozen, C17_ROOT
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c8_observer_runner import program_physical_consumed
from c9_server_admission import validate_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_x(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def gain(control, candidate):
    if control <= 0:
        raise GateError('paired gain denominator nonpositive')
    return 100 * (control - candidate) / control


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    args = p.parse_args()
    root = args.root.resolve()
    rows = []
    series = root / 'thermal-series.jsonl'
    for run_id, arm, mode, phase, order in SPEC:
        receipt = strict_json((root / f'{run_id}-receipt.json').read_text())
        idle = strict_json((root / f'{run_id}-idle.json').read_text())
        protocol, config, tasks = frozen(root, (run_id, arm, mode, phase, order))
        if protocol != strict_json((root / 'protocols' / f'{run_id}.json').read_text()) or \
                receipt['status'] != 'PASS_QUALIFIED' or idle['status'] != 'PASS' or \
                idle['qualifying_duration_s'] < 300 or idle['max_gap_qualifying_s'] > 1:
            raise GateError('frozen protocol/admission/run does not pass: ' + run_id)
        raw_path = root / 'raw' / f'{run_id}.json'
        raw = strict_json(raw_path.read_text())
        if receipt['raw_sha256'] != sha(raw_path) or raw['returncode'] != 0 or \
                raw['stop_reasons'] or len(raw['results']) != 1:
            raise GateError('raw identity/result invalid: ' + run_id)
        samples = [strict_json(line) for line in
                   (root / 'raw' / f'{run_id}.samples.jsonl').read_text().splitlines()]
        maxima = validate_receipt(protocol, config, raw, samples, root,
                                  run_id=run_id,
                                  protocol_filename='protocols/' + run_id + '.json',
                                  expected_results=1)
        cpu = summarize_samples(samples, require_safe=True)
        if maxima != receipt['maxima'] or cpu != receipt['cpu_telemetry']:
            raise GateError('resource/clock compact differs from raw: ' + run_id)
        normalized = strict_json((root / 'raw' / f'{run_id}.normalized.json').read_text())
        if validate_c2(normalized, {k: protocol[k] for k in PROTOCOL}) != receipt['server_gate']:
            raise GateError('normalized server gate differs: ' + run_id)
        request = raw['results'][0]
        elapsed = request['ended_s'] - request['started_s']
        if elapsed != receipt['request_elapsed_s'] or \
                request['usage']['prompt_tokens'] != 513 or \
                request['usage']['completion_tokens'] != 4 or \
                request['timings']['cache_n'] != 0:
            raise GateError('incomplete/different 513+4 request: ' + run_id)
        warning_active = [s for s in samples if s['cpu_diagnostics']['thermal_warning'] and
                          s['cpu_diagnostics']['request_active']]
        rows.append({'run_id': run_id, 'arm': arm, 'pair': phase, 'order': order,
                     'measurement_commit': receipt['measurement_commit'],
                     'status': receipt['status'], 'returncode': receipt['returncode'],
                     'stop_reasons': receipt['stop_reasons'], 'raw_sha256': sha(raw_path),
                     'input_token_ids_sha256': receipt['input_token_ids_sha256'],
                     'output_message_sha256': receipt['output_message_sha256'],
                     'request_elapsed_s': elapsed,
                     'prefill_s': receipt['prefill_s'], 'decode_s': receipt['decode_s'],
                     'idle_duration_s': idle['duration_s'],
                     'idle_start_temperatures_c': {'cpu': idle['end']['cpu_c'],
                                                   'gpu': idle['end']['gpu']['temperature_c'],
                                                   'nvme': idle['end']['nvme_c']},
                     'maxima': maxima, 'cpu_diagnostics': cpu,
                     'warning_active_effective_clock_min_mhz': min(
                         (s['cpu_diagnostics']['effective_clock_median_mhz'] for s in warning_active),
                         default=None),
                     'warning_active_effective_clock_median_mhz': median(
                         (s['cpu_diagnostics']['effective_clock_median_mhz'] for s in warning_active))
                         if warning_active else None,
                     'cgroup_end': raw['cgroup_end']})
    if len({row['input_token_ids_sha256'] for row in rows}) != 1:
        raise GateError('paired input token IDs differ')
    for arm in ('P8', 'P12'):
        if len({row['output_message_sha256'] for row in rows if row['arm'] == arm}) != 1:
            raise GateError('same-profile output message differs between fresh processes')
    pairs = []
    for phase in ('P1', 'P2'):
        members = [row for row in rows if row['pair'] == phase]
        if len(members) != 2 or len({row['arm'] for row in members}) != 2:
            raise GateError('pair incomplete: ' + phase)
        control = next(row for row in members if row['arm'] == 'P8')
        candidate = next(row for row in members if row['arm'] == 'P12')
        pairs.append({'pair': phase, 'execution_order': [row['arm'] for row in members],
                      'control_run_id': control['run_id'], 'candidate_run_id': candidate['run_id'],
                      'P8_request_s': control['request_elapsed_s'],
                      'P12_request_s': candidate['request_elapsed_s'],
                      'gain_request_pct': gain(control['request_elapsed_s'], candidate['request_elapsed_s']),
                      'gain_prefill_pct': gain(control['prefill_s'], candidate['prefill_s']),
                      'gain_decode_pct': gain(control['decode_s'], candidate['decode_s'])})
    idle_count = sum(strict_json((root / f'{run_id}-idle.json').read_text())['sample_count']
                     for run_id, *_ in SPEC)
    if len(series.read_text().splitlines()) != idle_count:
        raise GateError('idle raw line count differs from admissions')
    prior_c16_idle_s = 394.4515725659985
    prior_c17_idle_s = sum(strict_json(path.read_text())['duration_s']
                           for path in C17_ROOT.glob('*-idle.json'))
    c18_idle_s = sum(row['idle_duration_s'] for row in rows)
    server_s = program_physical_consumed()
    used_s = server_s + prior_c16_idle_s + prior_c17_idle_s + c18_idle_s
    timing = {'schema': 'c18-timing-pairs-v1', 'status': 'TWO_PAIRS_COMPLETE',
              'metric': 'completion-fenced API request seconds, 513 prompt + 4 completion tokens',
              'formula': '100*(P8-P12)/P8 for each paired metric', 'pairs': pairs,
              'median_gain_request_pct': median(x['gain_request_pct'] for x in pairs),
              'median_gain_prefill_pct': median(x['gain_prefill_pct'] for x in pairs),
              'median_gain_decode_pct': median(x['gain_decode_pct'] for x in pairs),
              'old_stopped_times_included': False}
    resources = {'schema': 'c18-resource-summary-v1', 'status': 'ALL_FOUR_RUNS_QUALIFIED',
                 'runs': rows, 'idle_series': {'path': 'thermal-series.jsonl',
                                              'sha256': sha(series),
                                              'sample_count': idle_count,
                                              'git_policy': 'raw local ignored'},
                 'thermal_flag_limit': 'ACPI Processor cooling observed; AMD direct hardware throttling flag unavailable',
                 'ambient_temperature': 'UNKNOWN'}
    prior = strict_json((root / 'prior-fails-preserved.json').read_text())
    if len(prior['runs']) != 6 or any(x['current_interpretation'] !=
                                     'FAIL_PROTOCOL_THERMAL_GUARD' for x in prior['runs']):
        raise GateError('prior protocol thermal stops not preserved')
    decision = {'schema': 'c18-decision-v1', 'status': 'THERMAL_RETTEST_PASS',
                'reason': 'P8 and P12 completed both new cold513 pairs under the prospective CPU100 policy with full outputs, fresh starts, zero stop reasons/swap/OOM/cap events and no observed ACPI Processor cooling.',
                'old_fails_preserved': [x['run_id'] for x in prior['runs']],
                'old_fail_interpretation': 'FAIL_PROTOCOL_THERMAL_GUARD; old source receipts unchanged',
                'pairs': pairs, 'runs': rows,
                'gates': {'preflight': 'PASS', 'idle_admission': 'PASS_FOUR',
                          'C18_cold513': 'PASS_FOUR',
                          'same_profile_output_message_repeat': 'PASS_P8_P12',
                          'same_profile_8k_full_logits': 'NOT_RUN',
                          'M3': 'NOT_RUN', 'M4': 'NOT_RUN',
                          'C15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED'},
                'claim_limits': ['Two paired server requests are descriptive; no p95, sustained or quality claim',
                                 'Output message checksum equality is not full-logit or distribution equality',
                                 'A 95 C warning was observed; no ACPI cooling but AMD direct hardware thermal flag unavailable',
                                 'Ambient temperature and attribution to placement or terminated competing app remain UNKNOWN',
                                 'P8/P12 cold ~513 prefill remains far above the proposed 30 s M4 cold512 goal'],
                'budget': {'physical_limit_s': 57600, 'raw_server_cumulative_s': server_s,
                           'c16_idle_s': prior_c16_idle_s, 'c17_idle_s': prior_c17_idle_s,
                           'c18_idle_s': c18_idle_s, 'accounted_physical_used_s': used_s,
                           'remaining_s': 57600-used_s,
                           'scope_note': 'Preflight model hashing and model-free work have no stopwatch receipts and are excluded from this physical sum'},
                'next_action': 'C19: new-identity P12 exact-prefix ON 512+128 synthetic server mechanism screen under CPU100/E18, using the frozen C13 input and 5-minute idle admission; then choose M3 session bridge or pivot based on actual cache_n/resources.',
                'default_changed': False,
                'closed_utc': datetime.now(timezone.utc).isoformat()}
    write_x(root / 'timing-pairs.json', timing)
    write_x(root / 'resource-summary.json', resources)
    write_x(root / 'decision.json', decision)
    compact = {name: sha(root / name) for name in
               ('protocol.json', 'preflight.json', 'prior-fails-preserved.json',
                'runs.jsonl', 'timing-pairs.json', 'resource-summary.json', 'decision.json')}
    write_x(root / 'manifest.json', {'schema': 'c18-results-manifest-v1',
                                    'compact_sha256': compact,
                                    'raw_server_sha256': {r['run_id']: r['raw_sha256'] for r in rows},
                                    'raw_idle_series_sha256': sha(series),
                                    'default_changed': False})
    print(json.dumps({'status': decision['status'], 'median_gain_request_pct':
                      timing['median_gain_request_pct'], 'accounted_physical_used_s': used_s},
                     allow_nan=False))


if __name__ == '__main__':
    main()
