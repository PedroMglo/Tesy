#!/usr/bin/env python3
"""Hash-check and summarize the C97/C98 one-pair server bridge."""

import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c98_server_wave_candidate as c98


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def gain(control, candidate):
    if type(control) not in (int, float) or type(candidate) not in (int, float) or control <= 0:
        raise GateError('C98 invalid paired timing denominator')
    return 100 * (control - candidate) / control


def checked_control():
    c98.control_evidence()
    root = c98.CONTROL
    manifest = strict_json((root/'manifest.json').read_text())
    for name, row in manifest['raw'].items():
        path = root/'raw'/name
        if path.stat().st_size != row['size_bytes'] or sha256(path) != row['sha256']:
            raise GateError('C97 control raw changed: '+name)
    return root


def analyze(root):
    control_root = checked_control()
    pre = strict_json((root/'preflight.json').read_text())
    if c98.control_evidence() != pre['control_evidence_sha256']:
        raise GateError('C98 frozen control differs')
    receipt = strict_json((root/'raw/candidate-receipt.json').read_text())
    if receipt['status'] != 'PASS_BRIDGE_TESTED_SCOPE' or \
       receipt['raw_sha256'] != sha256(root/'raw/c98-candidate01.json'):
        raise GateError('C98 candidate receipt/raw failed')
    control = strict_json((control_root/'raw/c97-control01.json').read_text())
    candidate = strict_json((root/'raw/c98-candidate01.json').read_text())
    cids = strict_json((control_root/'raw/c97-control01.tokenization.json').read_text())
    tids = strict_json((root/'raw/c98-candidate01.tokenization.json').read_text())
    if list(cids) != list(c98.prior.REQUESTS) or list(tids) != list(c98.prior.REQUESTS) or \
       len(control['results']) != 2 or len(candidate['results']) != 2:
        raise GateError('C97/C98 request/tokenization shape incomplete')
    rows = []
    for old, new in zip(control['results'], candidate['results']):
        key = old['id']
        if new['id'] != key:
            raise GateError('C98 request ID differs')
        ta, tb = old['timings'], new['timings']
        wall_a, wall_b = old['ended_s']-old['started_s'], new['ended_s']-new['started_s']
        vals = {'request_wall_s': (wall_a, wall_b),
                'prefill_s': (ta['prompt_ms']/1000, tb['prompt_ms']/1000),
                'decode_s': (ta['predicted_ms']/1000, tb['predicted_ms']/1000),
                'first_final_content_s': (
                    old['stream_metrics']['first_final_content_chunk_s'],
                    new['stream_metrics']['first_final_content_chunk_s'])}
        rows.append({'request_id': key, 'official_prompt_ids_equal': cids[key] == tids[key],
                     'assistant_message_equal': old['message'] == new['message'],
                     'assistant_message_sha256': c98.server.digest(old['message']),
                     'control_prompt_tokens': old['usage']['prompt_tokens'],
                     'candidate_prompt_tokens': new['usage']['prompt_tokens'],
                     'control_completion_tokens': old['usage']['completion_tokens'],
                     'candidate_completion_tokens': new['usage']['completion_tokens'],
                     'control_cached_tokens': ta['cache_n'],
                     'candidate_cached_tokens': tb['cache_n'],
                     'metrics': {name: {'control': a, 'candidate': b,
                                        'paired_gain_percent': gain(a, b)}
                                 for name, (a, b) in vals.items()},
                     'decode_tokens_per_s': {'control':ta['predicted_per_second'],
                                             'candidate':tb['predicted_per_second']}})
    starts = {arm: run['preflight']['resource_start_observation']
              for arm, run in (('control', control), ('candidate', candidate))}
    summary = {'schema': 'c98-server-bridge-summary-v1',
               'status': 'PASS_ONE_PAIR_BRIDGE_TESTED_SCOPE' if all(
                   x['official_prompt_ids_equal'] and x['assistant_message_equal'] for x in rows)
               else 'CROSS_ARM_INPUT_OR_OUTPUT_DIVERGENCE',
               'control_run_id': 'c97-control01', 'candidate_run_id': 'c98-candidate01',
               'control_measurement_commit': '586aa5488af58a8faa6159e8b53dead18017a55b',
               'candidate_measurement_commit': receipt['measurement_commit'],
               'rows': rows, 'start_observations': starts,
               'maxima': {'control': strict_json((control_root/'control-receipt.json').read_text())['maxima'],
                          'candidate': receipt['maxima']},
               'limitations': ['one sequential pair; not performance screening or confirmation',
                               'page-cache state uncontrolled; O_DIRECT configured, physical I/O attribution not established',
                               'equal assistant messages do not prove all full-model logits bitwise for these requests',
                               'synthetic two-turn history, not diverse quality or M4']}
    save_new(root/'bridge-summary.json', summary)
    raw = {path.name: {'size_bytes': path.stat().st_size, 'sha256': sha256(path)}
           for path in sorted((root/'raw').iterdir()) if path.is_file()}
    save_new(root/'manifest.json', {'schema':'c98-manifest-v1', 'raw':raw,
                                   'measurement_commit':receipt['measurement_commit'],
                                   'control_evidence_sha256':pre['control_evidence_sha256']})
    decision = {'schema':'c98-decision-v1', 'status':summary['status'],
                'measurement_commit':receipt['measurement_commit'],
                'control_run_id':'c97-control01','candidate_run_id':'c98-candidate01',
                'budget_consumed': {
                    'paired_server_process_elapsed_s': {
                        'control': control['elapsed_s'],
                        'candidate': candidate['elapsed_s'],
                        'sum': control['elapsed_s']+candidate['elapsed_s']},
                    'two_new_inventory_windows_minimum_s': 120,
                    'full_epoch_reconciliation': 'NOT_RUN'},
                'same_effective_prompt_ids_and_messages': summary['status']=='PASS_ONE_PAIR_BRIDGE_TESTED_SCOPE',
                'rows':rows,'maxima':summary['maxima'],
                'historical_failures_unchanged':['C48','C78','C96 candidate prelaunch','C97 candidate prelaunch'],
                'M3':'SESSION_MECHANICS_TESTED_SCOPE_LATENCY_OPEN', 'M4':'NOT_MET',
                'next_action':'Freeze two alternating fresh-process server pairs for 2043-token cold and actual-history warm requests, with cold prefill primary and incremental first-final/decode protection; then confirm survivors separately.',
                'default_changed':False}
    save_new(root/'decision.json', decision)
    save_new(root/'candidate-receipt.json', receipt)
    print(json.dumps({'status':summary['status'],'gains_percent':
                      {row['request_id']:{k:v['paired_gain_percent'] for k,v in row['metrics'].items()}
                       for row in rows}},allow_nan=False))


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        raise SystemExit('usage: c98_analyze_bridge.py ROOT')
    analyze(Path(sys.argv[1]).resolve())
