#!/usr/bin/env python3
"""Verify C104 raw and summarize the frozen same-binary OFF/ON diagnostic."""

import json
import math
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c104_server_wave_hot_toggle as c104

COMMIT = '91d7fd00f300ebd0df61b63d74ce473420cc311d'


def save_new(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def gain(off, on):
    if type(off) not in (int, float) or type(on) not in (int, float) or \
       not math.isfinite(off) or not math.isfinite(on) or off <= 0 or on <= 0:
        raise GateError('C104 nonpositive or invalid paired metric')
    return 100*(off-on)/off


def values(item):
    timing=item['timings']
    return {'prefill_s':timing['prompt_ms']/1000,
            'decode_s':timing['predicted_ms']/1000,
            'first_final_content_s':item['stream_metrics']['first_final_content_chunk_s'],
            'wall_s':item['ended_s']-item['started_s']}


def analyze(root):
    if strict_json((root/'toggle-policy.json').read_text()) != c104.policy(root):
        raise GateError('C104 frozen policy changed')
    raw={};receipts={};ids={}
    for run_id,arm,pair in c104.ORDER:
        receipt=strict_json((root/'raw'/f'{run_id}.receipt.json').read_text())
        if receipt.get('status') != 'PASS_TOGGLE_ARM_TESTED_SCOPE' or \
           receipt.get('arm') != arm or receipt.get('pair') != pair or \
           receipt.get('measurement_commit') != COMMIT or \
           receipt.get('raw_sha256') != sha256(root/'raw'/f'{run_id}.json'):
            raise GateError('C104 invalid receipt/raw: '+run_id)
        observed=strict_json((root/'raw'/f'{run_id}.json').read_text())
        if observed.get('returncode') != 0 or observed.get('stop_reasons') or \
           len(observed.get('results',[])) != 2 or receipt.get('completed_requests') != 2:
            raise GateError('C104 incomplete arm: '+run_id)
        receipts[run_id]=receipt;raw[run_id]=observed
        ids[run_id]=strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
    first=c104.ORDER[0][0]
    if [len(ids[first][key]) for key in c104.base.REQUESTS] != [2043,2081]:
        raise GateError('C104 prompt length changed')
    for run_id in raw:
        if ids[run_id] != ids[first] or \
           [item['message'] for item in raw[run_id]['results']] != \
           [item['message'] for item in raw[first]['results']]:
            raise GateError('C104 same-profile official IDs or assistant message mismatch')
        for i,item in enumerate(raw[run_id]['results']):
            if item['id'] != list(c104.base.REQUESTS)[i] or \
               item['timings']['cache_n'] != (0 if i==0 else 2044) or \
               not all(math.isfinite(v) and v>0 for v in values(item).values()):
                raise GateError('C104 request cache/timing invalid: '+run_id)
    pairs=[]
    for pair in (1,2):
        off_id=f'c104-p{pair}-off';on_id=f'c104-p{pair}-on'
        metric={}
        for i,label in ((0,'cold'),(1,'warm')):
            off=values(raw[off_id]['results'][i]);on=values(raw[on_id]['results'][i])
            for name in off:
                metric[f'{label}_{name}']={'off':off[name],'on':on[name],
                                          'paired_gain_percent':gain(off[name],on[name])}
        second_id=on_id if pair==2 else off_id
        pairs.append({'pair':pair,'order':[x[0] for x in c104.ORDER if x[2]==pair],
                      'off_run_id':off_id,'on_run_id':on_id,
                      'matched_start_wait_s':receipts[second_id]['matched_start']['duration_s'],
                      'metrics':metric})
    keys=['cold_prefill_s','warm_prefill_s','cold_decode_s','warm_decode_s',
          'cold_first_final_content_s','warm_first_final_content_s']
    medians={key:median(x['metrics'][key]['paired_gain_percent'] for x in pairs) for key in keys}
    both_decode_nonnegative=all(x['metrics'][name]['paired_gain_percent']>=0
                                for x in pairs for name in ('cold_decode_s','warm_decode_s'))
    both_decode_negative=all(x['metrics'][name]['paired_gain_percent']<0
                             for x in pairs for name in ('cold_decode_s','warm_decode_s'))
    status=('NO_ACTIVE_SKIP_DECODE_PENALTY_OBSERVED_TWO_PAIRS' if both_decode_nonnegative else
            'ACTIVE_SKIP_DECODE_PENALTY_OBSERVED_TWO_PAIRS' if both_decode_negative else
            'MIXED_DECODE_SIGNAL')
    timing={'schema':'c104-hot-toggle-timing-v1','status':status,'measurement_commit':COMMIT,
            'pairs':pairs,'median_paired_gain_percent':medians,
            'all_official_prompt_ids_equal':True,'all_assistant_messages_equal':True,
            'claim_limit':'two same-binary operational-start diagnostic pairs; no promotion or p95'}
    save_new(root/'timing-pairs.json',timing)
    resource={'schema':'c104-resources-v1','status':'PASS_ALL_FOUR_ARMS',
              'runs':{run_id:{'maxima':rec['maxima'],'elapsed_s':raw[run_id]['elapsed_s'],
                               'matched_start':rec['matched_start']}
                      for run_id,rec in receipts.items()},
              'model_process_elapsed_total_s':sum(v['elapsed_s'] for v in raw.values()),
              'matched_start_wait_total_s':sum(v['matched_start']['duration_s'] for v in receipts.values())}
    save_new(root/'resource-summary.json',resource)
    save_new(root/'manifest.json',{'schema':'c104-manifest-v1','measurement_commit':COMMIT,
             'raw':{p.name:{'size_bytes':p.stat().st_size,'sha256':sha256(p)}
                    for p in sorted((root/'raw').iterdir()) if p.is_file()}})
    with (root/'runs.jsonl').open('x') as out:
        for run_id,_,_ in c104.ORDER:
            rec=receipts[run_id]
            out.write(json.dumps({'run_id':run_id,'status':rec['status'],'arm':rec['arm'],
                                  'pair':rec['pair'],'measurement_commit':COMMIT,
                                  'raw_sha256':rec['raw_sha256'],
                                  'receipt_sha256':sha256(root/'raw'/f'{run_id}.receipt.json'),
                                  'completed_requests':2,'maxima':rec['maxima'],
                                  'default_changed':False},sort_keys=True,allow_nan=False)+'\n')
    decision={'schema':'c104-decision-v1','status':status,'measurement_commit':COMMIT,
              'gate_status':{'identity_outputs':'PASS','resources':'PASS','matched_start':'PASS',
                             'diagnostic':'COMPLETE'},
              'pairs':pairs,'median_paired_gain_percent':medians,
              'interpretation':'Active C75 wave skip did not cause a decode-duration penalty relative to C75 OFF in these two operational-start pairs; C100 cross-binary confirmation remains NO_GO due its protected regressions.' if both_decode_nonnegative else 'See per-pair signs; no general performance promotion.',
              'M3':'PARTIAL','M4':'NOT_MET','C100_NO_GO_unchanged':True,
              'historical_failures_unchanged':['C48','C78','C102 prelaunch','C103 matched start'],
              'budget_consumed':{'model_process_elapsed_s':resource['model_process_elapsed_total_s'],
                                 'matched_start_wait_s':resource['matched_start_wait_total_s'],
                                 'inventory_s_minimum':60},
              'limitations':['two diagnostic pairs, no p95/significance',
                             'operational starts vary across pairs; page cache uncontrolled',
                             'server output equality, not independent full attention/KV proof'],
              'next_action':'Do not relabel C100 as PASS. Inspect remaining decode/load bottleneck and select a different mechanism or C75 build-level explanation model-free before any new promotion test.',
              'default_changed':False}
    save_new(root/'decision.json',decision)
    print(json.dumps({'status':status,'paired_decode_gains':[
        {key:x['metrics'][key]['paired_gain_percent'] for key in ('cold_decode_s','warm_decode_s')}
        for x in pairs],'median_paired_gain_percent':medians},allow_nan=False))


if __name__=='__main__':
    import sys
    if len(sys.argv)!=2:raise SystemExit('usage: c104_analyze_hot_toggle.py ROOT')
    analyze(Path(sys.argv[1]).resolve())
