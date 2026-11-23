#!/usr/bin/env python3
"""Revalidate C99 raw and apply frozen two-pair server-screen policy."""

import json
import math
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c99_server_wave_screen as c99


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def gain(control, candidate):
    if type(control) not in (int, float) or type(candidate) not in (int, float) or \
       not math.isfinite(control) or not math.isfinite(candidate) or control <= 0 or candidate <= 0:
        raise GateError('C99 invalid paired timing')
    return 100*(control-candidate)/control


def metrics(item):
    timing = item['timings']
    return {'prefill_s':timing['prompt_ms']/1000,
            'decode_s':timing['predicted_ms']/1000,
            'request_wall_s':item['ended_s']-item['started_s'],
            'first_final_content_s':item['stream_metrics']['first_final_content_chunk_s']}


def analyze(root):
    policy = strict_json((root/'screen-policy.json').read_text())
    if policy != c99.policy(root):
        raise GateError('C99 frozen policy changed')
    raw = {}
    receipts = {}
    ids = {}
    for run_id, _, _ in c99.ORDER:
        receipt = strict_json((root/'raw'/f'{run_id}.receipt.json').read_text())
        if receipt.get('status') != 'PASS_SCREEN_ARM_TESTED_SCOPE' or \
           receipt.get('measurement_commit') != '3b0d9e6c3f2f0995f97b0eca85ee7af96c1017f2' or \
           receipt.get('raw_sha256') != sha256(root/'raw'/f'{run_id}.json'):
            raise GateError('C99 arm receipt/raw invalid: '+run_id)
        observed = strict_json((root/'raw'/f'{run_id}.json').read_text())
        if observed.get('stop_reasons') or observed.get('returncode') != 0 or \
           len(observed.get('results', [])) != 2:
            raise GateError('C99 arm output incomplete: '+run_id)
        raw[run_id] = observed
        receipts[run_id] = receipt
        ids[run_id] = strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
    first_id = c99.ORDER[0][0]
    if any(ids[name] != ids[first_id] or \
           [x['message'] for x in raw[name]['results']] != \
           [x['message'] for x in raw[first_id]['results']]
           for name,_,_ in c99.ORDER):
        raise GateError('C99 full official token IDs or assistant messages differ across arms')
    if [len(ids[first_id][key]) for key in c99.base.REQUESTS] != [2043,2081]:
        raise GateError('C99 official prompt lengths differ from frozen observed input')
    pairs = []
    for number in (1,2):
        control_id=f'c99-p{number}-control';candidate_id=f'c99-p{number}-candidate'
        control=raw[control_id]['results'];candidate=raw[candidate_id]['results']
        if [x['id'] for x in control] != list(c99.base.REQUESTS) or \
           [x['id'] for x in candidate] != list(c99.base.REQUESTS):
            raise GateError('C99 request identity differs')
        for i,(a,b) in enumerate(zip(control,candidate)):
            expected_cached = 0 if i == 0 else 2044
            if a['timings']['cache_n'] != expected_cached or \
               b['timings']['cache_n'] != expected_cached or \
               a['usage']['completion_tokens'] != b['usage']['completion_tokens']:
                raise GateError('C99 cache or completion count differs')
        values = {}
        for i,label in ((0,'cold'),(1,'warm')):
            a,b=metrics(control[i]),metrics(candidate[i])
            for key in a:
                values[f'{label}_{key}']={'control':a[key],'candidate':b[key],
                                           'paired_gain_percent':gain(a[key],b[key])}
        pairs.append({'pair':number, 'run_order':[x[0] for x in c99.ORDER if x[2]==number],
                      'control_run_id':control_id,'candidate_run_id':candidate_id,
                      'matched_start_wait_s':receipts[candidate_id if number==1 else control_id]
                          ['matched_start']['duration_s'],
                      'metrics':values})
    selected=['cold_prefill_s','cold_first_final_content_s','warm_first_final_content_s',
              'cold_decode_s','warm_decode_s']
    medians={name:median([row['metrics'][name]['paired_gain_percent'] for row in pairs])
             for name in selected}
    go = (medians['cold_prefill_s']>=5 and
          all(row['metrics']['cold_prefill_s']['paired_gain_percent']>0 for row in pairs) and
          all(medians[name]>=-5 for name in selected[1:]))
    status = 'SCREEN_GO_CONFIRMATION_PENDING' if go else 'NO_GO_SERVER_SCREEN'
    timing={'schema':'c99-server-screen-timing-v1','status':status,
            'measurement_commit':'3b0d9e6c3f2f0995f97b0eca85ee7af96c1017f2',
            'pairs':pairs,'median_paired_gain_percent':medians,
            'all_official_prompt_ids_equal':True,'all_assistant_messages_equal':True,
            'claim_limit':'two pairs on one synthetic two-turn workload; no confirmation/p95/quality claim'}
    save_new(root/'timing-pairs.json',timing)
    resources={'schema':'c99-server-screen-resources-v1','status':'PASS_ALL_FOUR_ARMS',
               'runs':{name: {'maxima':rec['maxima'],
                              'matched_start':rec['matched_start'],
                              'elapsed_s':raw[name]['elapsed_s']}
                       for name,rec in receipts.items()},
               'model_process_elapsed_total_s':sum(x['elapsed_s'] for x in raw.values()),
               'matched_start_wait_total_s':sum(
                   rec['matched_start']['duration_s'] for rec in receipts.values())}
    save_new(root/'resource-summary.json',resources)
    manifest={'schema':'c99-manifest-v1','measurement_commit':timing['measurement_commit'],
              'raw':{path.name:{'size_bytes':path.stat().st_size,'sha256':sha256(path)}
                     for path in sorted((root/'raw').iterdir()) if path.is_file()}}
    save_new(root/'manifest.json',manifest)
    decision={'schema':'c99-decision-v1','status':status,'gate_status':{
                  'identity_outputs':'PASS', 'matched_start':'PASS', 'resources':'PASS',
                  'server_screen':'GO' if go else 'NO_GO'},
              'measurement_commit':timing['measurement_commit'],
              'pairs':pairs,'median_paired_gain_percent':medians,
              'reference_coverage':'C93-C95 8K P12 observed numeric scope; no independent attention/KV certification',
              'budget_consumed':{'model_process_elapsed_s':resources['model_process_elapsed_total_s'],
                                 'matched_start_wait_s':resources['matched_start_wait_total_s'],
                                 'inventory_s_minimum':60,
                                 'full_epoch_reconciliation':'NOT_RUN'},
              'historical_failures_unchanged':['C48','C78','C96 candidate prelaunch','C97 candidate prelaunch'],
              'M3':'SESSION_MECHANICS_TESTED_SCOPE_LATENCY_OPEN','M4':'NOT_MET',
              'limitations':['two pairs are screening, not confirmation or p95',
                             'synthetic prompt/history; no diverse quality test',
                             'page cache uncontrolled; no physical expert I/O attribution'],
              'next_action':('Freeze three new alternating C35/C75 server pairs with same profile/workload; '
                             'confirm cold prefill median gain >=8%, all three pairs positive and '
                             'protected medians >=-5%, before M3 diverse session qualification.'
                             if go else 'Preserve negative screen and pivot to next mechanism/phase.'),
              'default_changed':False}
    save_new(root/'decision.json',decision)
    print(json.dumps({'status':status,'median_paired_gain_percent':medians,
                      'cold_prefill_pair_gains':[row['metrics']['cold_prefill_s']['paired_gain_percent']
                                                 for row in pairs]},allow_nan=False))


if __name__=='__main__':
    import sys
    if len(sys.argv)!=2:
        raise SystemExit('usage: c99_analyze_screen.py ROOT')
    analyze(Path(sys.argv[1]).resolve())
