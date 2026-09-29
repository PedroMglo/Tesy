#!/usr/bin/env python3
"""Fresh C75 slots32/40 eight-task holdout with C120 start inventory."""

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
import c131_holdout_grade as holdout


ROOT_NAME = 'c131-holdout8-20260929T1847Z'
ORDER = (('c131-control-quality8','control'),('c131-candidate-quality8','candidate'))
CAP = 18*GIB
REPO = Path(__file__).resolve().parents[1]


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def tasks():
    return [(x['id'],dict(x,cache_prompt=False,
                          chat_template_kwargs={'tesy_template_date':'2026-09-28',
                                                'reasoning_effort':'medium'}))
            for x in holdout.workload()['tasks']]


def budget(root, remaining):
    prior_path = REPO/'results/c130b-slots40-quality-20260929T1808Z/epoch-checkpoint.json'
    prior = strict_json(prior_path.read_text())
    now = datetime.now(timezone.utc)
    wall = (datetime.fromisoformat('2026-09-29T13:31:15+00:00')+
            timedelta(hours=12)-now).total_seconds()
    intervals=[]
    for run_id,_ in ORDER:
        path=root/'raw'/(run_id+'.receipt.json')
        if not path.is_file():continue
        row=strict_json(path.read_text())
        a,b=datetime.fromisoformat(row['started_utc']),datetime.fromisoformat(row['ended_utc'])
        if b<a:raise GateError('C131 receipt chronology invalid')
        intervals.append({'run_id':run_id,'seconds':(b-a).total_seconds(),
                          'status':row['status']})
    charged=prior['physical_charged_upper_estimate_s']+120+sum(x['seconds'] for x in intervals)
    physical=28800-charged
    reserve=remaining*(3600+60)+600+3600
    if min(wall,physical)<reserve:
        raise GateError('C131 two arms plus sustained-session reserve not admitted')
    return {'schema':'c131-budget-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(prior_path),'completed':intervals,
            'physical_charged_upper_estimate_s':charged,
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall,'remaining_arms':remaining,
            'holdout_and_session_reserve_s':reserve}


def quality_policy(root):
    return {'schema':'c131-holdout-policy-v1','status':'FROZEN_BEFORE_ANY_HOLDOUT_RESPONSE',
            'order':[run_id for run_id,_ in ORDER],
            'control_profile':'C75 waves ON slots32',
            'candidate_profile':'C75 waves ON slots40',
            'target':'same original GPT-OSS120B GGUF, medium, context8192',
            'workload_sha256':sha256(holdout.TASKS),
            'grader_sha256':sha256(holdout.__file__),
            'answer_gate':'candidate must PASS every task passed by control; all 8 candidate PASS required for full holdout quality PASS',
            'stop_gate':'all eight requests natural finish, official tokens, graded outputs, identity/resources/inventory valid',
            'paired_timing_claim':'NONE; quality comparison only',
            'cap_bytes':CAP,'swap_max_bytes':0,'default_changed':False}


def make(root, spec):
    run_id,arm=spec
    protocol,config=base.make(root,'candidate')
    ids=[name for name,_ in tasks()]
    command=config['server_command']
    pos=command.index('--moe-stream-cache')+1
    if command[pos]!='32s' or config['explicit_env']!={'TESY_CPU_WAVE_SKIP_PARKED':'1'}:
        raise GateError('C131 C75 base profile changed')
    if arm=='candidate':command[pos]='40s'
    config.update(suite='c131holdout',task_ids=ids,pretokenize=True,
                  freeze_token_ids=True,append_previous_assistant_to_next=False,
                  allow_cache_prompt=False,enforce_output_reserve=True,
                  stream_requests=True,inter_request_idle_s=0,
                  total_timeout_s=3600,
                  request_policy={'mode':'prospective-holdout8','attempts':1,
                                  'max_tokens':3072,'temperature':0,'seed':42,
                                  'reasoning_effort':'medium','per_request_timeout_s':600})
    for key in ('dynamic_cache_min_common','dynamic_cache_max_lost',
                'prompt_token_ranges','record_monotonic_request_markers'):
        config.pop(key,None)
    protocol.pop('trace',None)
    protocol['schema_version']='c131-protocol-v1'
    protocol['protocol_id']=run_id+'-v1'
    protocol['expected_request_ids']=ids
    protocol['identity'].update(config_sha256=server.digest(config),
        workload_sha256=sha256(holdout.TASKS),
        input_sha256={'workloads/c131_holdout8.json':sha256(holdout.TASKS)})
    parent=protocol.pop('c97')
    protocol['c131']={'run_id':run_id,'arm':arm,'slots_per_layer':32 if arm=='control' else 40,
                      'model_stat':parent['model_stat'],'backend_tree':parent['backend_tree'],
                      'runner_sha256':sha256(__file__),'grader_sha256':sha256(holdout.__file__),
                      'quality_policy_sha256':sha256(root/'quality-policy.json'),
                      'prior_c129_decision_sha256':sha256(REPO/'results/c129-slots40-confirm-20260929T1735Z/decision.json')}
    protocol['start_inventory']={'schema':'c120-start-inventory-v1',
                                 'duration_s':60,'max_age_s':3,
                                 'policy_sha256':sha256(root/'resource-policy.json')}
    validate_resource_protocol(protocol)
    return protocol,config


def freeze(root):
    if root.name!=ROOT_NAME or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C131 fresh root/raw/protocols required')
    control=holdout.self_test()
    save_new(root/'model-free-tests.json',{'schema':'c131-model-free-v1',
        'workload_sha256':sha256(holdout.TASKS),
        'grader_sha256':sha256(holdout.__file__),'gold_mutant':control})
    save_new(root/'budget-admission.json',budget(root,len(ORDER)))
    save_new(root/'quality-policy.json',quality_policy(root))
    for spec in ORDER:
        p,c=make(root,spec)
        save_new(root/'protocols'/(spec[0]+'.json'),p)
        save_new(root/(spec[0]+'-config.json'),c)
    names=(['snapshot.json','resource-policy.json','session-input.json',
            'quality-policy.json','model-free-tests.json']+
           [f'protocols/{x[0]}.json' for x in ORDER]+
           [f'{x[0]}-config.json' for x in ORDER])
    save_new(root/'preflight.json',{'schema':'c131-freeze-v1',
        'status':'FROZEN_NOT_MEASURED','utc':datetime.now(timezone.utc).isoformat(),
        'files':{name:sha256(root/name) for name in names},
        'runner_sha256':sha256(__file__)})


def frozen(root,spec):
    pre=strict_json((root/'preflight.json').read_text())
    if pre['status']!='FROZEN_NOT_MEASURED' or pre['runner_sha256']!=sha256(__file__) or \
       any(sha256(root/name)!=digest for name,digest in pre['files'].items()) or \
       quality_policy(root)!=strict_json((root/'quality-policy.json').read_text()):
        raise GateError('C131 source/protocol/fixture changed')
    p,c=make(root,spec)
    if p!=strict_json((root/'protocols'/(spec[0]+'.json')).read_text()) or \
       c!=strict_json((root/(spec[0]+'-config.json')).read_text()):
        raise GateError('C131 frozen arm changed')
    return p,c


def validate(root,spec,p,c,raw):
    run_id=spec[0]
    samples=[strict_json(line) for line in
             (root/'raw'/(run_id+'.samples.jsonl')).read_text().splitlines()]
    maxima=validate_receipt(p,c,raw,samples,root,run_id=run_id,
                            protocol_filename=f'protocols/{run_id}.json',
                            expected_results=8)
    ids=strict_json((root/'raw'/(run_id+'.tokenization.json')).read_text())
    if list(ids)!=p['expected_request_ids'] or \
       [x['id'] for x in raw['results']]!=p['expected_request_ids']:
        raise GateError('C131 task/tokenization identity invalid')
    results=[]
    for item in raw['results']:
        usage,stream=item.get('usage'),item.get('stream_metrics')
        if item.get('finish_reason')!='stop' or not stream or \
           stream.get('done_observed') is not True or \
           usage.get('prompt_tokens')!=len(ids[item['id']]) or \
           not 0<usage.get('completion_tokens',0)<3072:
            raise GateError('C131 incomplete task/output/usage')
        detail=holdout.grade(item['id'],item['message'].get('content'))
        if detail['status']=='VALIDATOR_ENV_ERROR':
            raise GateError('C131 validator isolation unavailable')
        results.append({'id':item['id'],'category':item['category'],
                        'status':detail['status'],'detail':detail,
                        'completion_tokens':usage['completion_tokens'],
                        'first_final_content_s':stream.get('first_final_content_chunk_s'),
                        'message_sha256':server.digest(item['message'])})
    return maxima,results


def run(root,spec,commit):
    run_id=spec[0]
    started=datetime.now(timezone.utc)
    launched=False;raw=None;inv=None;maxima=None;results=None;failure=None
    try:
        budget(root,len(ORDER)-ORDER.index(spec))
        if base.git('rev-parse','HEAD')!=commit or base.git('status','--porcelain') or \
           relevant_environment(os.environ):
            raise GateError('C131 measurement HEAD/worktree/environment changed')
        scope=server.cgroup_state()
        if not scope or scope['memory_max']!=CAP or scope['swap_max']!=0:
            raise GateError('C131 E18/zero-swap parent scope invalid')
        p,c=frozen(root,spec)
        if spec!=ORDER[0]:
            prior=strict_json((root/'raw'/(ORDER[0][0]+'.receipt.json')).read_text())
            if prior['status']!='PASS_HOLDOUT_ARM_EVALUATED':
                raise GateError('C131 control arm did not complete')
        no_other_model()
        policy=strict_json((root/'resource-policy.json').read_text())
        power={key:policy['power'][key] for key in ('source','profile')}
        inv=collect(root,run_id,policy=policy,cap_bytes=CAP,
                    expected_power=power,duration_s=60)
        save_new(root/'raw'/(run_id+'.start-inventory.receipt.json'),inv)
        require_inventory(root,run_id,inv,policy=policy,cap_bytes=CAP,
                          expected_power=power,duration_s=60)
        args=SimpleNamespace(run_id=run_id,protocol=root/'protocols'/(run_id+'.json'),
                             suite='c131holdout',model='target120b')
        code=server.run(args,p,c,tasks(),MODEL)
        launched=(root/'raw'/(run_id+'.launch.json')).is_file()
        raw=strict_json((root/'raw'/(run_id+'.json')).read_text())
        maxima,results=validate(root,spec,p,c,raw)
        if code!=0:raise GateError('C131 server runner exit failure')
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}'
        launched=(root/'raw'/(run_id+'.launch.json')).is_file()
    if raw is None and (root/'raw'/(run_id+'.json')).is_file():
        raw=strict_json((root/'raw'/(run_id+'.json')).read_text())
    status=('PASS_HOLDOUT_ARM_EVALUATED' if failure is None else
            'FAIL_RESOURCES_OR_EVIDENCE' if launched else 'FAIL_HARNESS_PREMODEL')
    receipt={'schema':'c131-arm-receipt-v1','run_id':run_id,'arm':spec[1],
             'measurement_commit':commit,'started_utc':started.isoformat(),
             'ended_utc':datetime.now(timezone.utc).isoformat(),
             'status':status,'reason':failure,'model_launch_observed':launched,
             'completed_requests':len(raw['results']) if raw else 0,
             'stop_reasons':raw.get('stop_reasons') if raw else None,
             'inventory_receipt_sha256':sha256(root/'raw'/(run_id+'.start-inventory.receipt.json')) if inv else None,
             'raw_sha256':sha256(root/'raw'/(run_id+'.json')) if raw else None,
             'maxima':maxima,'results':results,'default_changed':False}
    save_new(root/'raw'/(run_id+'.receipt.json'),receipt)
    print(json.dumps({'status':status,'run_id':run_id,
                      'pass_count':sum(x['status']=='PASS' for x in results) if results else None,
                      'reason':failure},allow_nan=False))
    return 0 if failure is None else 1


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path);ap.add_argument('--run-id',choices=[x[0] for x in ORDER])
    ap.add_argument('--measurement-commit');a=ap.parse_args()
    root=a.root.resolve()
    if a.mode=='freeze':freeze(root)
    else:
        if not a.run_id or not a.measurement_commit:ap.error('run requires ID and commit')
        raise SystemExit(run(root,next(x for x in ORDER if x[0]==a.run_id),a.measurement_commit))


if __name__=='__main__':
    main()
