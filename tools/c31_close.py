#!/usr/bin/env python3
"""Close the finite C31 source-log diagnostic without changing measured raw."""

import datetime as dt
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c31-cache-reproduction-20260927T2342Z')
IDS = ('c31-d1-prefix2048', 'c31-d2-prefix2048', 'c31-d3-prefix2048')


def save_new(path, value):
    with path.open('x') as out:
        json.dump(value, out, sort_keys=True, indent=2, allow_nan=False)
        out.write('\n')


def main():
    receipts = []
    source_logs = {}
    for run_id in IDS:
        receipt_path = ROOT / f'{run_id}-receipt.json'
        receipt = strict_json(receipt_path.read_text())
        raw_path = ROOT / 'raw' / f'{run_id}.json'
        diagnostic = strict_json((ROOT / f'{run_id}-diagnostic.json').read_text())
        log_path = ROOT / 'raw' / f'{run_id}.stderr'
        log = log_path.read_text()
        if receipt['run_id'] != run_id or receipt['status'] != 'PASS_BRIDGE' or \
                receipt['server_returncode'] != 0 or receipt['stop_reasons'] or \
                receipt['raw_sha256'] != sha256(raw_path) or \
                diagnostic['receipt_sha256'] != sha256(receipt_path) or \
                diagnostic['status'] != receipt['status'] or \
                receipt['actual_common_prefix_ids'] != 2035 or \
                len(receipt['results']) != 2 or \
                receipt['results'][1]['timings']['cache_n'] != 2036 or \
                receipt['results'][1]['timings']['prompt_n'] != 143 or \
                receipt['maxima']['swap_bytes'] != 0 or \
                receipt['server_gate']['status'] != 'PASS':
            raise GateError(f'C31 evidence changed or failed: {run_id}')
        if log.count('old: ...') != 1 or log.count('new: ...') != 1 or \
                'cached n_tokens = 2036' not in log:
            raise GateError(f'C31 source cache markers incomplete: {run_id}')
        source_logs[run_id] = {
            'stderr_sha256': sha256(log_path),
            'old_new_token_window_count': 1,
            'cached_2036_marker': True,
            'full_prompt_reprocessing_marker':
                'forcing full prompt re-processing due to lack of cache data' in log,
        }
        receipts.append(receipt)

    with (ROOT / 'runs.jsonl').open('x') as out:
        for receipt in receipts:
            out.write(json.dumps(receipt, sort_keys=True, allow_nan=False) + '\n')
    save_new(ROOT / 'resource-summary.json', {
        'schema': 'c31-resource-summary-v1', 'timing_promotable': False,
        'runs': [
            {'run_id': r['run_id'], 'idle_s': r['idle']['duration_s'],
             'maxima': r['maxima'], 'cpu_diagnostics': r['cpu_diagnostics'],
             'server_gate': r['server_gate']} for r in receipts],
    })
    save_new(ROOT / 'session-summary.json', {
        'schema': 'c31-session-diagnostic-v1', 'synthetic_two_turn': True,
        'source_logs': source_logs,
        'runs': [
            {'run_id': r['run_id'], 'actual_common_prefix_ids': r['actual_common_prefix_ids'],
             'first_turn_s': r['results'][0]['request_elapsed_s'],
             'second_turn_s': r['results'][1]['request_elapsed_s'],
             'second_cache_n': r['results'][1]['timings']['cache_n'],
             'second_prompt_n': r['results'][1]['timings']['prompt_n'],
             'second_first_final_content_s':
                 r['results'][1]['stream_metrics']['first_final_content_chunk_s']}
            for r in receipts],
        'interpretation': 'three instrumented cache hits; C29 cache_n35 failure persists; no miss-rate estimate',
    })
    prior_idle = sum(strict_json(p.read_text())['duration_s'] for p in
                     Path('results').glob('c*-*/**/*-idle.json'))
    decision = {
        'schema': 'c31-cache-reproduction-decision-v1',
        'status': 'INCOMPLETE_DIAGNOSTIC_THREE_CACHE_HITS',
        'reason': 'C29 cache_n35 miss was not reproduced in three frozen fresh-process source-log runs',
        'runs': list(IDS), 'measurement_commits': [r['measurement_commit'] for r in receipts],
        'C29_failure_preserved': {'cache_n': 35, 'status': 'FAIL_RESOURCES_OR_EVIDENCE'},
        'observed_second_cache_n': [r['results'][1]['timings']['cache_n'] for r in receipts],
        'instrumented_timing_promotable': False,
        'miss_cause': 'UNKNOWN_NOT_REPRODUCED',
        'm3': 'PARTIAL_TRUE_CONVERSATION_CACHE_UNRELIABLE', 'm4': 'NOT_RUN',
        'c15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED',
        'physical_execution_s_including_idle': program_physical_consumed() + prior_idle,
        'next_action': 'C32 source-only feasibility/accounting for full SWA cache versus compact checkpoint fallback; choose bounded mechanism test from capacity and source, without another identical cache repetition',
        'default_changed': False,
    }
    save_new(ROOT / 'decision.json', decision)
    save_new(ROOT / 'manifest.json', {
        'schema': 'c31-closure-manifest-v1',
        'protocol_sha256': sha256(ROOT / 'protocol.json'),
        'protocol_run_sha256': {run_id: sha256(ROOT / 'protocols' / f'{run_id}.json')
                                for run_id in IDS},
        'raw_sha256': {r['run_id']: r['raw_sha256'] for r in receipts},
        'receipt_sha256': {run_id: sha256(ROOT / f'{run_id}-receipt.json') for run_id in IDS},
        'source_log_sha256': {run_id: source_logs[run_id]['stderr_sha256'] for run_id in IDS},
        'decision_sha256': sha256(ROOT / 'decision.json'),
        'closed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    with (ROOT / 'LEDGER.md').open('a') as out:
        out.write('\n- D3 `c31-d3-prefix2048`: PASS_BRIDGE; second cache 2036, prompt eval 143, second 32.516 s (instrumented). Three frozen diagnostics all hit; C29 cache_n35 FAIL persists and cause is UNKNOWN. C31 closes INCOMPLETE_DIAGNOSTIC_THREE_CACHE_HITS. C32 source/capacity feasibility is next; no further identical repetition. C15 remains source-only; M3 partial, M4 NOT_RUN, default unchanged.\n')
    print(json.dumps({'status': decision['status'], 'runs': list(IDS),
                      'physical_execution_s_including_idle': decision['physical_execution_s_including_idle']}))


if __name__ == '__main__':
    main()
