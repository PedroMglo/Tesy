#!/usr/bin/env python3
"""C132: varied twenty-turn slots40 session with a measured active block."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL, validate_receipt
from c17_thermal_recovery import no_other_model
from c118_start_inventory import collect, require_inventory
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import relevant_environment, sha256
import c112_nominal_session_base as base


REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = 'c132-diverse-active-session-20260929T1939Z'
RUN_ID = 'c132-c75-slots40-diverse20'
WORKLOAD = REPO/'workloads/c132_diverse_session.json'
CAP = 18*GIB
EPOCH_START = datetime.fromisoformat('2026-09-29T13:31:15+00:00')
SCHEDULE = [0]*15 + [600]*5


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def workload():
    row = strict_json(WORKLOAD.read_text())
    tasks = row['tasks']
    if row['schema'] != 'c132-diverse-session-workload-v1' or \
       row['template_date'] != '2026-09-29' or len(tasks) != 20 or \
       len({x['id'] for x in tasks}) != 20:
        raise GateError('C132 workload identity/shape invalid')
    return row


def tasks():
    template = {'tesy_template_date':workload()['template_date'],
                'reasoning_effort':'medium'}
    return [(item['id'], {'id':item['id'],'category':item['category'],
                         'messages':[{'role':'user','content':item['message']}],
                         'cache_prompt':True,'chat_template_kwargs':template})
            for item in workload()['tasks']]


def make(root):
    protocol, config = base.make(root,'candidate')
    command = config['server_command']
    pos = command.index('--moe-stream-cache')+1
    if command[pos] != '32s' or config['explicit_env'] != {'TESY_CPU_WAVE_SKIP_PARKED':'1'}:
        raise GateError('C132 C75 profile changed')
    command[pos] = '40s'
    ids = [item['id'] for item in workload()['tasks']]
    config.update(suite='c132session',task_ids=ids,pretokenize=True,
                  freeze_token_ids=True,append_previous_assistant_to_next=True,
                  allow_cache_prompt=True,enforce_output_reserve=True,
                  stream_requests=True,inter_request_idle_s=0,
                  inter_request_idle_schedule_s=SCHEDULE,
                  dynamic_cache_min_common=100,dynamic_cache_max_lost=32,
                  total_timeout_s=5700,
                  request_policy={'mode':'diverse-active-session','attempts':1,
                                  'max_tokens':512,'temperature':0,'seed':42,
                                  'reasoning_effort':'medium','per_request_timeout_s':600})
    for key in ('prompt_token_ranges','record_monotonic_request_markers'):
        config.pop(key,None)
    protocol.pop('trace',None)
    protocol['schema_version']='c132-protocol-v1'
    protocol['protocol_id']=RUN_ID+'-v1'
    protocol['expected_request_ids']=ids
    protocol['identity'].update(config_sha256=server.digest(config),
        workload_sha256=sha256(WORKLOAD),
        input_sha256={'workloads/c132_diverse_session.json':sha256(WORKLOAD)})
    parent = protocol.pop('c97')
    protocol['c132']={'model_stat':parent['model_stat'],
                      'backend_tree':parent['backend_tree'],
                      'numeric_profile':'C75 waves ON, slots40, P12, n_ctx8192',
                      'runner_sha256':sha256(__file__),
                      'server_runner_sha256':sha256(server.__file__),
                      'prior_c131_decision_sha256':sha256(REPO/'results/c131-holdout8-20260929T1847Z/decision.json'),
                      'idle_schedule_s':SCHEDULE,
                      'active_block_requests':15,
                      'active_block_min_s':900,
                      'total_session_min_s':3600,
                      'claim':'varied assistant-history continuity and active load, not general quality or M4'}
    protocol['start_inventory']={'schema':'c120-start-inventory-v1',
                                 'duration_s':60,'max_age_s':3,
                                 'policy_sha256':sha256(root/'resource-policy.json')}
    validate_resource_protocol(protocol)
    return protocol,config


def budget():
    path=REPO/'results/c131-holdout8-20260929T1847Z/epoch-checkpoint.json'
    prior=strict_json(path.read_text())['budget']
    now=datetime.now(timezone.utc)
    physical=prior['physical_remaining_lower_bound_s']
    wall=(EPOCH_START+timedelta(hours=12)-now).total_seconds()
    reserve=5700+60+600
    if min(wall,physical)<reserve:
        raise GateError('C132 session and closure not admitted by epoch budget')
    return {'schema':'c132-budget-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(path),
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall,'reserved_s':reserve,
            'physical_cap_s':28800,'wall_cap_s':43200}


def freeze(root):
    if root.name!=ROOT_NAME or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C132 fresh root/raw/protocols required')
    if server.session_idle_schedule({'inter_request_idle_schedule_s':SCHEDULE},20)!= \
       [float(x) for x in SCHEDULE]:
        raise GateError('C132 idle schedule model-free mismatch')
    save_new(root/'budget-admission.json',budget())
    save_new(root/'session-contract.json',{'schema':'c132-session-contract-v1',
        'status':'FROZEN_BEFORE_MODEL','run_id':RUN_ID,
        'quality_gate':'20 natural completions; each response satisfies its predeclared required phrases',
        'duration_gate_s':3600,'first_15_consecutive_active_gate_s':900,
        'first_15_max_inter_request_gap_s':10,
        'last_5_idle_before_each_s':600,
        'cache_gate':'actual previous assistant messages, official token arrays, generated-prefix cache checked by c2',
        'resource_gate':'C132 protocol policy E18/zero swap and per-arm 60-second start inventory',
        'limits':['one workload, one physical session','no general functional-quality or M4 claim']})
    protocol,config=make(root)
    save_new(root/'protocols'/f'{RUN_ID}.json',protocol)
    save_new(root/f'{RUN_ID}-config.json',config)
    names=['snapshot.json','resource-policy.json','session-input.json','session-contract.json',
           f'protocols/{RUN_ID}.json',f'{RUN_ID}-config.json']
    save_new(root/'preflight.json',{'schema':'c132-freeze-v1',
        'status':'FROZEN_NOT_MEASURED','utc':datetime.now(timezone.utc).isoformat(),
        'files':{name:sha256(root/name) for name in names},
        'runner_sha256':sha256(__file__),
        'server_runner_sha256':sha256(server.__file__),
        'workload_sha256':sha256(WORKLOAD)})


def frozen(root):
    pre=strict_json((root/'preflight.json').read_text())
    if pre['status']!='FROZEN_NOT_MEASURED' or \
       pre['runner_sha256']!=sha256(__file__) or \
       pre['server_runner_sha256']!=sha256(server.__file__) or \
       pre['workload_sha256']!=sha256(WORKLOAD) or \
       any(sha256(root/name)!=digest for name,digest in pre['files'].items()):
        raise GateError('C132 source/workload/protocol freeze changed')
    p,c=make(root)
    if p!=strict_json((root/'protocols'/f'{RUN_ID}.json').read_text()) or \
       c!=strict_json((root/f'{RUN_ID}-config.json').read_text()):
        raise GateError('C132 frozen profile/config changed')
    return p,c


def grade(item, specification):
    text=item['message'].get('content')
    if type(text) is not str or not text.strip():
        return {'status':'FAIL','reason':'empty final content'}
    folded=text.casefold()
    required=specification.get('required',[])
    any_groups=specification.get('required_any',[])
    missing=[word for word in required if word.casefold() not in folded]
    missing.extend('|'.join(group) for group in any_groups
                   if not any(word.casefold() in folded for word in group))
    return {'status':'PASS' if not missing else 'FAIL','missing':missing}


def validate(root,p,c,raw):
    samples=[strict_json(line) for line in
             (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    maxima=validate_receipt(p,c,raw,samples,root,run_id=RUN_ID,
                            protocol_filename=f'protocols/{RUN_ID}.json',
                            expected_results=20)
    ids=strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())
    results=raw['results']; specifications=workload()['tasks']
    if list(ids)!=p['expected_request_ids'] or \
       [x['id'] for x in results]!=p['expected_request_ids']:
        raise GateError('C132 official tokenization/request identities differ')
    details=[]
    for item,spec in zip(results,specifications):
        usage,stream=item.get('usage'),item.get('stream_metrics')
        if item.get('finish_reason')!='stop' or not stream or \
           stream.get('done_observed') is not True or \
           usage.get('prompt_tokens')!=len(ids[item['id']]) or \
           not 0<usage.get('completion_tokens',0)<c['request_policy']['max_tokens']:
            raise GateError(f'C132 incomplete request/usage: {item["id"]}')
        details.append({'id':item['id'],'category':item['category'],
                        'grade':grade(item,spec),
                        'prompt_tokens':usage['prompt_tokens'],
                        'completion_tokens':usage['completion_tokens'],
                        'cache_n':item['timings']['cache_n'],
                        'first_final_content_s':stream.get('first_final_content_chunk_s'),
                        'message_sha256':server.digest(item['message'])})
    active=results[14]['ended_s']-results[0]['started_s']
    total=results[-1]['ended_s']-results[0]['started_s']
    gaps=[b['started_s']-a['ended_s'] for a,b in zip(results,results[1:])]
    valid_time=active>=900 and total>=3600 and \
        all(0<=gap<=10 for gap in gaps[:14]) and \
        all(gap>=599.5 for gap in gaps[14:])
    return maxima,details,{'active_block_s':active,'session_span_s':total,
                           'request_active_sum_s':sum(x['ended_s']-x['started_s'] for x in results),
                           'adjacent_gaps_s':gaps,'duration_pass':valid_time}


def run(root,commit):
    started=datetime.now(timezone.utc)
    launched=False;raw=None;inventory=None;maxima=None;details=None;timing=None;failure=None
    try:
        budget()
        if base.git('rev-parse','HEAD')!=commit or base.git('status','--porcelain') or \
           relevant_environment(os.environ):
            raise GateError('C132 measurement HEAD/worktree/environment changed')
        scope=server.cgroup_state()
        if not scope or scope['memory_max']!=CAP or scope['swap_max']!=0:
            raise GateError('C132 E18/zero-swap scope invalid')
        p,c=frozen(root)
        no_other_model()
        policy=strict_json((root/'resource-policy.json').read_text())
        power={key:policy['power'][key] for key in ('source','profile')}
        inventory=collect(root,RUN_ID,policy=policy,cap_bytes=CAP,
                          expected_power=power,duration_s=60)
        save_new(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json',inventory)
        require_inventory(root,RUN_ID,inventory,policy=policy,cap_bytes=CAP,
                          expected_power=power,duration_s=60)
        args=SimpleNamespace(run_id=RUN_ID,protocol=root/'protocols'/f'{RUN_ID}.json',
                             suite='c132session',model='target120b')
        code=server.run(args,p,c,tasks(),MODEL)
        launched=(root/'raw'/f'{RUN_ID}.launch.json').is_file()
        raw=strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        maxima,details,timing=validate(root,p,c,raw)
        if code!=0:raise GateError('C132 server runner exit failure')
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}'
        launched=(root/'raw'/f'{RUN_ID}.launch.json').is_file()
    if raw is None and (root/'raw'/f'{RUN_ID}.json').is_file():
        raw=strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
    status=('PASS_DIVERSE_ACTIVE_SESSION' if failure is None and
            timing['duration_pass'] and all(x['grade']['status']=='PASS' for x in details) else
            'SESSION_QUALITY_OR_DURATION_NO_GO' if failure is None else
            'FAIL_RESOURCES_OR_EVIDENCE' if launched else 'FAIL_HARNESS_PREMODEL')
    receipt={'schema':'c132-session-receipt-v1','run_id':RUN_ID,
             'measurement_commit':commit,'started_utc':started.isoformat(),
             'ended_utc':datetime.now(timezone.utc).isoformat(),
             'status':status,'reason':failure,'model_launch_observed':launched,
             'completed_requests':len(raw['results']) if raw else 0,
             'stop_reasons':raw.get('stop_reasons') if raw else None,
             'inventory_receipt_sha256':sha256(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json') if inventory else None,
             'raw_sha256':sha256(root/'raw'/f'{RUN_ID}.json') if raw else None,
             'maxima':maxima,'results':details,'timing':timing,'default_changed':False}
    save_new(root/'raw'/f'{RUN_ID}.receipt.json',receipt)
    print(json.dumps({'status':status,'completed':receipt['completed_requests'],
                      'quality_pass_count':sum(x['grade']['status']=='PASS' for x in details) if details else None,
                      'active_block_s':timing['active_block_s'] if timing else None,
                      'session_span_s':timing['session_span_s'] if timing else None,
                      'reason':failure},allow_nan=False))
    return 0 if status=='PASS_DIVERSE_ACTIVE_SESSION' else 1


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path)
    ap.add_argument('--measurement-commit')
    args=ap.parse_args();root=args.root.resolve()
    if args.mode=='freeze':freeze(root)
    else:
        if not args.measurement_commit:ap.error('run requires measurement commit')
        raise SystemExit(run(root,args.measurement_commit))


if __name__=='__main__':
    main()
