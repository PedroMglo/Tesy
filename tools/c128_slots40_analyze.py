#!/usr/bin/env python3
"""Independent C128 gate: inventory, identity, equal work, paired server timing."""

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from c118_start_inventory import require_inventory
from run_bounded import sha256
import c117_operational_nominal_server as previous
import c128_slots40_server as campaign


METRICS = ('warm_decode_s','warm_first_final_s','warm_prefill_s',
           'cold_decode_s','cold_first_final_s','cold_prefill_s')
PROTECTED = tuple(metric for metric in METRICS if metric != 'warm_decode_s')


def screen_gate(pairs):
    if len(pairs) != 2 or any(set(pair['gain_percent']) != set(METRICS) for pair in pairs):
        raise GateError('C128 incomplete paired metrics')
    medians = {key:median(pair['gain_percent'][key] for pair in pairs) for key in METRICS}
    if not all(pair['same_work'] for pair in pairs):
        return 'INCONCLUSIVE_OUTPUT_DIVERGENCE', medians
    go = (medians['warm_decode_s'] >= 8 and
          all(pair['gain_percent']['warm_decode_s'] > 0 for pair in pairs) and
          all(medians[key] >= -5 for key in PROTECTED))
    return ('SCREEN_GO_SLOTS40_NOMINAL153' if go else 'NO_GO_SLOTS40_NOMINAL153'), medians


def positive(value, name):
    if type(value) not in (float,int) or not math.isfinite(value) or value <= 0:
        raise GateError(f'C128 invalid {name}')
    return float(value)


def arm(root, spec, commit, policy):
    run_id, role, pair = spec
    raw_dir = root/'raw'
    receipt_path = raw_dir/(run_id+'.receipt.json')
    inv_path = raw_dir/(run_id+'.start-inventory.receipt.json')
    launch_path = raw_dir/(run_id+'.launch.json')
    raw_path = raw_dir/(run_id+'.json')
    receipt, inv, launch, raw = [strict_json(path.read_text()) for path in
                                 (receipt_path,inv_path,launch_path,raw_path)]
    protocol_path = root/'protocols'/(run_id+'.json')
    config_path = root/(run_id+'-config.json')
    protocol, config = strict_json(protocol_path.read_text()), strict_json(config_path.read_text())
    pre = strict_json((root/'preflight.json').read_text())
    if sha256(protocol_path) != pre['protocol_sha256'][run_id] or \
       sha256(config_path) != pre['config_sha256'][run_id] or \
       receipt.get('run_id') != run_id or receipt.get('measurement_commit') != commit or \
       receipt.get('status') != 'PASS_SCREEN_ARM_TESTED_SCOPE' or \
       receipt.get('raw_sha256') != sha256(raw_path) or \
       receipt.get('start_inventory_receipt_sha256') != sha256(inv_path) or \
       receipt.get('model_launch_observed') is not True or \
       launch.get('run_id') != run_id or \
       launch.get('start_inventory',{}).get('receipt_sha256') != sha256(inv_path):
        raise GateError(f'C128 arm provenance incomplete: {run_id}')
    launch_time = datetime.fromisoformat(launch['start_inventory']['popen_invoked_utc'])
    power = {key:policy['power'][key] for key in ('source','profile')}
    require_inventory(root,run_id,inv,policy=policy,cap_bytes=campaign.campaign.CAP,
                      expected_power=power,duration_s=60,now=launch_time,max_age_s=3)
    expected_slots = '32s' if role == 'control' else '40s'
    command = config['server_command']
    if command[command.index('--moe-stream-cache')+1] != expected_slots or \
       config['explicit_env'] != {'TESY_CPU_WAVE_SKIP_PARKED':'1'} or \
       protocol['c120']['c128_numeric_profile']['slots_per_layer'] != int(expected_slots[:-1]) or \
       protocol['identity']['backend_sha'] != campaign.BACKEND[2] or \
       raw.get('returncode') != 0 or raw.get('stop_reasons') != [] or \
       len(raw.get('results',[])) != 2:
        raise GateError(f'C128 model/profile/resource failure: {run_id}')
    # Reuse the original answer, marker, token and prospective resource gate.
    maxima = previous.validate_run(root,spec,protocol,config,raw)
    if maxima != receipt['maxima']:
        raise GateError(f'C128 maxima changed: {run_id}')
    first, second = raw['results']
    metrics = {'warm_decode_s':positive(second['timings']['predicted_ms']/1000,'warm decode'),
               'warm_first_final_s':positive(second['stream_metrics']['first_final_content_chunk_s'],'warm final'),
               'warm_prefill_s':positive(second['timings']['prompt_ms']/1000,'warm prefill'),
               'cold_decode_s':positive(first['timings']['predicted_ms']/1000,'cold decode'),
               'cold_first_final_s':positive(first['stream_metrics']['first_final_content_chunk_s'],'cold final'),
               'cold_prefill_s':positive(first['timings']['prompt_ms']/1000,'cold prefill')}
    tokens_path = raw_dir/(run_id+'.tokenization.json')
    return {'run_id':run_id,'role':role,'pair':pair,'metrics':metrics,
            'completion_tokens':[x['usage']['completion_tokens'] for x in raw['results']],
            'prompt_tokens':[x['usage']['prompt_tokens'] for x in raw['results']],
            'cached_tokens':second['timings']['cache_n'],
            'evaluated_tokens':second['timings']['prompt_n'],
            'tokenization_sha256':sha256(tokens_path),
            'messages':[x['message'] for x in raw['results']],
            'raw_sha256':sha256(raw_path),'receipt_sha256':sha256(receipt_path),
            'start_temperature_c':receipt['matched_start']['temperature_c'],
            'maxima':maxima}


def analyze(root):
    campaign.configure()
    pre = strict_json((root/'preflight.json').read_text())
    screen = strict_json((root/'confirm-policy.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    if screen != campaign.screen_policy(root) or sha256(root/'confirm-policy.json') != pre['confirm_policy_sha256'] or \
       screen['order'] != [row[0] for row in campaign.ORDER] or \
       screen['primary'] != 'warm decode_s':
        raise GateError('C128 screen policy changed')
    first = strict_json((root/'raw'/(campaign.ORDER[0][0]+'.receipt.json')).read_text())
    commit = first['measurement_commit']
    if type(commit) is not str or len(commit) != 40:
        raise GateError('C128 measurement commit invalid')
    runs = [arm(root,spec,commit,policy) for spec in campaign.ORDER]
    pairs = []
    for number in (1,2):
        control = next(x for x in runs if x['pair']==number and x['role']=='control')
        candidate = next(x for x in runs if x['pair']==number and x['role']=='candidate')
        same_work = (control['completion_tokens']==candidate['completion_tokens'] and
                     control['prompt_tokens']==candidate['prompt_tokens'] and
                     control['cached_tokens']==candidate['cached_tokens'] and
                     control['evaluated_tokens']==candidate['evaluated_tokens'] and
                     control['tokenization_sha256']==candidate['tokenization_sha256'] and
                     control['messages']==candidate['messages'])
        gains = {key:100*(control['metrics'][key]-candidate['metrics'][key])/control['metrics'][key]
                 for key in METRICS}
        pairs.append({'pair':number,'control':control['run_id'],
                      'candidate':candidate['run_id'],'same_work':same_work,
                      'gain_percent':gains,
                      'start_delta_candidate_minus_control_c':
                          [b-a for a,b in zip(control['start_temperature_c'],
                                              candidate['start_temperature_c'])]})
    status, medians = screen_gate(pairs)
    for row in runs:
        row.pop('messages')
    timing = {'schema':'c128-timing-v1','measurement_commit':commit,
              'runs':runs,'pairs':pairs,'median_paired_gain_percent':medians,
              'primary':'warm_decode_s','protected':list(PROTECTED)}
    decision = {'schema':'c128-decision-v1','status':status,
                'measurement_commit':commit,'median_paired_gain_percent':medians,
                'pairs':pairs,'primary':'warm_decode_s','protected':list(PROTECTED),
                'M4':'NOT_DEMONSTRATED','default_changed':False,'publication':'LOCAL_ONLY',
                'next_action':('confirm and qualify slots40 if screen GO; otherwise retain C75 slots32 as operational candidate')}
    manifest = {'schema':'c128-manifest-v1','measurement_commit':commit,
                'raw':{p.name:{'bytes':p.stat().st_size,'sha256':sha256(p)}
                       for p in sorted((root/'raw').iterdir()) if p.is_file()}}
    return timing, decision, manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root',type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    for name,row in zip(('timing-pairs.json','decision.json','manifest.json'),analyze(root)):
        campaign.campaign.save_new(root/name,row)
    print(json.dumps({'status':strict_json((root/'decision.json').read_text())['status']}))


if __name__ == '__main__':
    main()
