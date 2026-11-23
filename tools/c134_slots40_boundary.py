#!/usr/bin/env python3
"""C134: original 7936+256 retrieval boundary on C75 waves ON/slots40."""

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
import c41_boundary as old_boundary


REPO=Path(__file__).resolve().parents[1]
ROOT_NAME='c134-slots40-boundary-20260929T2131Z'
RUN_ID='c134-c75-slots40-boundary7936'
CAP=18*GIB
EPOCH_START=datetime.fromisoformat('2026-09-29T13:31:15+00:00')


def save_new(path,value):
    with Path(path).open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def task(root):
    row,prompt=old_boundary.input_text(root)
    return [(RUN_ID,{'id':RUN_ID,'category':'synthetic-long-context-retrieval',
                     'messages':[{'role':'user','content':prompt}],
                     'cache_prompt':False,
                     'chat_template_kwargs':{'tesy_template_date':row['template_date'],
                                             'reasoning_effort':'medium'}})]


def make(root):
    protocol,config=base.make(root,'candidate')
    command=config['server_command']
    pos=command.index('--moe-stream-cache')+1
    if command[pos]!='32s' or config['explicit_env']!={'TESY_CPU_WAVE_SKIP_PARKED':'1'}:
        raise GateError('C134 base C75 profile changed')
    command[pos]='40s'
    config.update(suite='c134boundary',task_ids=[RUN_ID],pretokenize=True,
                  freeze_token_ids=True,append_previous_assistant_to_next=False,
                  allow_cache_prompt=False,enforce_output_reserve=True,
                  stream_requests=True,inter_request_idle_s=0,
                  require_natural_stop=True,
                  prompt_token_ranges={RUN_ID:[7936,7936]},
                  total_timeout_s=2400,
                  request_policy={'mode':'original-8k-retrieval','attempts':1,
                                  'max_tokens':256,'temperature':0,'seed':42,
                                  'reasoning_effort':'medium','per_request_timeout_s':2100})
    for key in ('dynamic_cache_min_common','dynamic_cache_max_lost',
                'record_monotonic_request_markers'):
        config.pop(key,None)
    protocol.pop('trace',None)
    protocol['schema_version']='c134-protocol-v1'
    protocol['protocol_id']=RUN_ID+'-v1'
    protocol['expected_request_ids']=[RUN_ID]
    protocol['identity'].update(config_sha256=server.digest(config),
        workload_sha256=sha256(root/'input.json'),
        input_sha256={'input.json':sha256(root/'input.json')})
    parent=protocol.pop('c97')
    protocol['c134']={'model_stat':parent['model_stat'],
                      'backend_tree':parent['backend_tree'],
                      'numeric_profile':'C75 waves ON P12 slots40 ctx8192 KV F16',
                      'runner_sha256':sha256(__file__),
                      'server_runner_sha256':sha256(server.__file__),
                      'original_c42_decision_sha256':sha256(REPO/'results/c42-8k-boundary-20260928T0741Z/decision.json'),
                      'prior_c133_decision_sha256':sha256(REPO/'results/c133-diverse-active-session-20260929T2000Z/decision.json'),
                      'expected_official_prompt_tokens':7936,
                      'max_output_tokens':256,
                      'expected_answer':'Q7M2N9',
                      'claim':'functional/context/resource admission at 8K on slots40; no causal latency comparison'}
    protocol['start_inventory']={'schema':'c120-start-inventory-v1',
                                 'duration_s':60,'max_age_s':3,
                                 'policy_sha256':sha256(root/'resource-policy.json')}
    validate_resource_protocol(protocol)
    return protocol,config


def budget():
    path=REPO/'results/c133-diverse-active-session-20260929T2000Z/epoch-checkpoint.json'
    prior=strict_json(path.read_text())
    now=datetime.now(timezone.utc)
    wall=(EPOCH_START+timedelta(hours=12)-now).total_seconds()
    physical=prior['physical_remaining_lower_bound_s']
    reserve=2400+60+600+1800
    if min(wall,physical)<reserve:
        raise GateError('C134 boundary plus remaining discriminant/closure not admitted')
    return {'schema':'c134-budget-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(path),
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall,'reserved_s':reserve,
            'post_boundary_discriminant_reserve_s':1800}


def freeze(root):
    if root.name!=ROOT_NAME or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C134 fresh root/raw/protocols required')
    bridge=old_boundary.tokenizer_bridge(root)
    save_new(root/'model-free-tests.json',{'schema':'c134-model-free-v1',
        'original_c41_tokenizer_bridge':bridge,
        'input_sha256':sha256(root/'input.json'),
        'server_entrypoint':'C120/C131/C133 real path already exercised; C134 new physical path NOT_RUN'})
    save_new(root/'budget-admission.json',budget())
    protocol,config=make(root)
    save_new(root/'protocols'/f'{RUN_ID}.json',protocol)
    save_new(root/f'{RUN_ID}-config.json',config)
    names=['snapshot.json','resource-policy.json','session-input.json','input.json',
           'model-free-tests.json',f'protocols/{RUN_ID}.json',f'{RUN_ID}-config.json']
    save_new(root/'preflight.json',{'schema':'c134-freeze-v1',
        'status':'FROZEN_NOT_MEASURED','utc':datetime.now(timezone.utc).isoformat(),
        'files':{name:sha256(root/name) for name in names},
        'runner_sha256':sha256(__file__),
        'server_runner_sha256':sha256(server.__file__)})


def frozen(root):
    pre=strict_json((root/'preflight.json').read_text())
    if pre['status']!='FROZEN_NOT_MEASURED' or \
       pre['runner_sha256']!=sha256(__file__) or \
       pre['server_runner_sha256']!=sha256(server.__file__) or \
       any(sha256(root/name)!=digest for name,digest in pre['files'].items()):
        raise GateError('C134 frozen source/protocol changed')
    p,c=make(root)
    if p!=strict_json((root/'protocols'/f'{RUN_ID}.json').read_text()) or \
       c!=strict_json((root/f'{RUN_ID}-config.json').read_text()):
        raise GateError('C134 effective profile changed')
    return p,c


def validate(root,p,c,raw):
    samples=[strict_json(line) for line in
             (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    maxima=validate_receipt(p,c,raw,samples,root,run_id=RUN_ID,
                            protocol_filename=f'protocols/{RUN_ID}.json',
                            expected_results=1)
    ids=strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())
    item=raw['results'][0]
    usage=item.get('usage');stream=item.get('stream_metrics')
    if list(ids)!=[RUN_ID] or len(ids[RUN_ID])!=7936 or \
       item['id']!=RUN_ID or usage.get('prompt_tokens')!=7936 or \
       usage.get('total_tokens',8193)>8192 or \
       not 0<usage.get('completion_tokens',0)<256 or \
       item.get('finish_reason')!='stop' or \
       not stream or stream.get('done_observed') is not True or \
       item.get('timings',{}).get('cache_n')!=0:
        raise GateError('C134 official boundary/finish/cache gate failed')
    answer=item['message'].get('content')
    if type(answer) is not str or answer.strip()!='Q7M2N9':
        raise GateError('C134 retrieval answer mismatch')
    return maxima,{'official_input_tokens':len(ids[RUN_ID]),
                   'official_input_token_ids_sha256':server.digest(ids[RUN_ID]),
                   'output_tokens':usage['completion_tokens'],
                   'answer_sha256':server.digest(answer),
                   'request_wall_s':item['ended_s']-item['started_s'],
                   'first_final_content_s':stream.get('first_final_content_chunk_s'),
                   'finish_reason':item['finish_reason']}


def run(root,commit):
    started=datetime.now(timezone.utc)
    launched=False;raw=None;inventory=None;maxima=None;detail=None;failure=None
    try:
        budget()
        if base.git('rev-parse','HEAD')!=commit or base.git('status','--porcelain') or \
           relevant_environment(os.environ):
            raise GateError('C134 measurement HEAD/worktree/environment changed')
        scope=server.cgroup_state()
        if not scope or scope['memory_max']!=CAP or scope['swap_max']!=0:
            raise GateError('C134 E18/zero-swap scope invalid')
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
                             suite='c134boundary',model='target120b')
        code=server.run(args,p,c,task(root),MODEL)
        launched=(root/'raw'/f'{RUN_ID}.launch.json').is_file()
        raw=strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        maxima,detail=validate(root,p,c,raw)
        if code!=0:raise GateError('C134 server runner exit failure')
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}'
        launched=(root/'raw'/f'{RUN_ID}.launch.json').is_file()
    if raw is None and (root/'raw'/f'{RUN_ID}.json').is_file():
        raw=strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
    status=('PASS_SLOTS40_BOUNDARY_RETRIEVAL' if failure is None else
            'FAIL_BOUNDARY_OR_EVIDENCE' if launched else 'FAIL_HARNESS_PREMODEL')
    receipt={'schema':'c134-boundary-receipt-v1','run_id':RUN_ID,
             'measurement_commit':commit,'started_utc':started.isoformat(),
             'ended_utc':datetime.now(timezone.utc).isoformat(),
             'status':status,'reason':failure,'model_launch_observed':launched,
             'completed_requests':len(raw['results']) if raw else 0,
             'stop_reasons':raw.get('stop_reasons') if raw else None,
             'inventory_receipt_sha256':sha256(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json') if inventory else None,
             'raw_sha256':sha256(root/'raw'/f'{RUN_ID}.json') if raw else None,
             'maxima':maxima,'detail':detail,'default_changed':False}
    save_new(root/'raw'/f'{RUN_ID}.receipt.json',receipt)
    print(json.dumps({'status':status,'completed':receipt['completed_requests'],
                      'detail':detail,'reason':failure},allow_nan=False))
    return 0 if failure is None else 1


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
