#!/usr/bin/env python3
"""Close the frozen C40 functional comparison without replacing raw evidence."""

import datetime as dt
import json
from pathlib import Path
import statistics

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c40-quality-recovery-20260928T0528Z')
STOCK = Path('results/c38-quality12-20260928T0353Z/c38-stock20-receipt.json')
INDEX = Path('results/120b-program-index.json')
INTERRUPTION = Path('results/c39-quality-recovery-20260928T0438Z/interruption.json')


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def checked_receipt(path, raw):
    row = strict_json(path.read_text())
    if row['status'] != 'PASS_COMPLETE_12_TASKS' or row['completed_requests'] != 12 or \
       len(row['results']) != 12 or row['raw_sha256'] != sha256(raw) or \
       row['stop_reasons'] or row['returncode'] != 0 or row['runner_returncode'] != 0 or \
       row['maxima']['swap_bytes'] != 0:
        raise GateError(f'incomplete C40/C38 receipt: {path}')
    ids = [item['id'] for item in row['results']]
    if len(ids) != len(set(ids)):
        raise GateError(f'duplicate task IDs: {path}')
    return row


def summary(row):
    results = row['results']
    final_times = [x['first_final_content_s'] for x in results
                   if x['first_final_content_s'] is not None]
    return {
        'run_id': row['run_id'],
        'status': row['status'],
        'pass_count': row['pass_count'],
        'task_count': len(results),
        'measurement_commit': row['measurement_commit'],
        'elapsed_s': row['elapsed_s'],
        'task_wall_total_s': sum(x['wall_s'] for x in results),
        'task_wall_median_s': statistics.median(x['wall_s'] for x in results),
        'first_final_content_median_s': statistics.median(final_times) if final_times else None,
        'resolved_by_deadline_s': {str(t): sum(x['status'] == 'PASS' and x['wall_s'] <= t
                                               for x in results) for t in (30, 120, 600)},
        'task_statuses': [{'id': x['id'], 'status': x['status'], 'wall_s': x['wall_s'],
                           'first_final_content_s': x['first_final_content_s'],
                           'completion_tokens': x['completion_tokens'],
                           'message_sha256': x['message_sha256']} for x in results],
        'maxima': row['maxima'],
        'raw_sha256': row['raw_sha256'],
    }


def main():
    protocol = strict_json((ROOT / 'protocol.json').read_text())
    if protocol['schema'] != 'c40-quality-recovery-protocol-v1' or \
       protocol['run_order'] != ['p8', 'p12']:
        raise GateError('C40 protocol identity differs')
    arms = {arm: checked_receipt(ROOT / f'c40-{arm}-receipt.json',
                                 ROOT / 'raw' / f'c40-{arm}.json')
            for arm in ('p8', 'p12')}
    stock = checked_receipt(STOCK, STOCK.parent / 'raw' / 'c38-stock20.json')
    ids = [x['id'] for x in arms['p8']['results']]
    if [x['id'] for x in arms['p12']['results']] != ids or \
       [x['id'] for x in stock['results']] != ids or \
       protocol['reused_stock20_receipt_sha256'] != sha256(STOCK):
        raise GateError('C40 task ordering/comparator identity differs')
    if arms['p8']['pass_count'] != 12 or arms['p12']['pass_count'] != 12 or \
       stock['pass_count'] != 11:
        raise GateError('C40 functional counts differ')
    index = strict_json(INDEX.read_text())
    if any(unit['identity'] == 'c40' for unit in index['units']):
        raise GateError('C40 already indexed')
    idle = sum(strict_json(path.read_text())['duration_s']
               for path in Path('results').glob('c*-*/**/*-idle.json'))
    interrupted = strict_json(INTERRUPTION.read_text())['physical_runtime_charged_s']
    consumed = program_physical_consumed() + idle + interrupted
    if consumed > 16 * 3600:
        raise GateError('C40 physical budget exceeded')
    for name in ('quality-summary.json', 'resource-summary.json',
                 'manifest.json', 'runs.jsonl', 'decision.json'):
        if (ROOT / name).exists():
            raise GateError(f'C40 no-replace output exists: {name}')
    p12 = summary(arms['p12'])
    p12.update(schema='c40-arm-quality-summary-v1',
               claim_limit='one P12 run, synthetic suite; no timing distribution or M4 claim')
    p12_path = ROOT / 'p12-quality-summary.json'
    if p12_path.exists():
        if strict_json(p12_path.read_text()) != p12:
            raise GateError('partial C40 P12 summary differs')
    else:
        save_new(p12_path, p12)
    quality = {
        'schema': 'c40-quality-summary-v1',
        'suite_sha256': protocol['workload_sha256'],
        'arms': {arm: summary(row) for arm, row in arms.items()},
        'stock20': summary(stock),
        'no_loss_vs_p8': all(p['status'] == 'PASS' or b['status'] != 'PASS'
                             for b, p in zip(arms['p8']['results'], arms['p12']['results'])),
        'limits': ['12 synthetic tasks only', 'one complete run per 120B profile',
                   'stock20 uses C38 monitor provenance',
                   'profile outputs and completion lengths differ; elapsed difference is descriptive',
                   '8K boundary, true assistant-history session and sustained functional quality NOT_RUN'],
    }
    save_new(ROOT / 'quality-summary.json', quality)
    resource = {'schema': 'c40-resource-summary-v1',
                'arms': {arm: {'maxima': row['maxima'], 'cpu_diagnostics': row['cpu_diagnostics'],
                               'idle_end': row['idle']['end'], 'idle_status': row['idle']['status']}
                         for arm, row in arms.items()},
                'zero_swap_oom_guards_pass': True}
    save_new(ROOT / 'resource-summary.json', resource)
    raw_manifest = {}
    for path in sorted((ROOT / 'raw').iterdir()):
        if path.is_file():
            raw_manifest[str(path)] = {'sha256': sha256(path), 'size_bytes': path.stat().st_size}
    raw_manifest[str(ROOT / 'thermal-series.jsonl')] = {
        'sha256': sha256(ROOT / 'thermal-series.jsonl'),
        'size_bytes': (ROOT / 'thermal-series.jsonl').stat().st_size}
    save_new(ROOT / 'manifest.json', {'schema': 'c40-manifest-v1', 'raw_files': raw_manifest,
                                      'stock20_receipt_sha256': sha256(STOCK),
                                      'protocol_sha256': sha256(ROOT / 'protocol.json')})
    with (ROOT / 'runs.jsonl').open('x') as stream:
        for arm, row in arms.items():
            stream.write(json.dumps({'run_id': row['run_id'], 'arm': arm,
                                     'measurement_commit': row['measurement_commit'],
                                     'status': row['status'], 'returncode': row['returncode'],
                                     'stop_reasons': row['stop_reasons'],
                                     'raw_sha256': row['raw_sha256'],
                                     'elapsed_s': row['elapsed_s'],
                                     'idle_start': row['idle']['start'],
                                     'maxima': row['maxima']}, sort_keys=True, allow_nan=False) + '\n')
    decision = {'schema': 'c40-decision-v1', 'status': 'PROFILE_CANDIDATE_TESTED_SCOPE',
                'P8': 'PASS_12_OF_12', 'P12': 'PASS_12_OF_12', 'stock20': 'PASS_11_OF_12',
                'no_loss_vs_p8': True, 'M3': 'PARTIAL_C37_SYNTHETIC_SESSION',
                'M4': 'NOT_RUN', 'C15_model': 'NOT_RUN', 'default_changed': False,
                'measurement_commits': {arm: row['measurement_commit'] for arm, row in arms.items()},
                'old_failures_preserved': ['C38 P8 FAIL_TELEMETRY',
                                          'C39 P8 FAIL_ORCHESTRATOR_INTERRUPTION',
                                          'six C9-C17 CPU95 FAIL_PROTOCOL_THERMAL_GUARD'],
                'physical_budget_consumed_s': consumed,
                'physical_budget_remaining_s': 16 * 3600 - consumed,
                'claims': ['P12 and P8 each solved the same 12 synthetic tasks under the frozen cap',
                           'P12 did not lose a task solved by P8 in this suite',
                           'one-arm elapsed times are descriptive only'],
                'not_run': ['7936+256 8K context boundary', 'true assistant-history continuity',
                            'M4 candidate thresholds', 'C15 full-model critical-path diagnostic'],
                'next_action': 'C41 prospective 7936-input+256-output 8K boundary and retrieval/continuity gate under E18; then choose session or wave bottleneck test',
                'closed_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    save_new(ROOT / 'decision.json', decision)
    index['units'].append({'identity': 'c40', 'root': str(ROOT),
                           'status': decision['status']})
    index['milestones']['M3'] = decision['M3']
    index['milestones']['M4'] = decision['M4']
    index['next_action'] = decision['next_action']
    index['updated_utc'] = decision['closed_utc']
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'status': decision['status'], 'quality': 'P8=12/12 P12=12/12 stock20=11/12',
                      'physical_budget_remaining_s': decision['physical_budget_remaining_s']},
                     allow_nan=False))


if __name__ == '__main__':
    main()
