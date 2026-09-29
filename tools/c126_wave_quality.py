#!/usr/bin/env python3
"""C126: original C40 twelve-task quality fixture on the confirmed C75 profile."""

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
from c38_quality_grade import grade, self_test, workload
from c118_start_inventory import collect, require_inventory
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import relevant_environment, sha256
import c112_nominal_session_base as base


RUN_ID = 'c126-c75-quality12'
CAP = 18 * GIB
EPOCH_START = datetime.fromisoformat('2026-09-29T13:31:15+00:00')
ROOT_NAME = 'c126-wave-quality-20260929T1610Z'


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def tasks():
    return [(x['id'], dict(x, cache_prompt=False,
                           chat_template_kwargs={'tesy_template_date':'2026-09-28',
                                                 'reasoning_effort':'medium'}))
            for x in workload()['tasks']]


def make(root):
    protocol, config = base.make(root, 'candidate')
    ids = [name for name, _ in tasks()]
    config.update(suite='c126quality', task_ids=ids, pretokenize=True,
                  freeze_token_ids=True, append_previous_assistant_to_next=False,
                  allow_cache_prompt=False, enforce_output_reserve=True,
                  stream_requests=True, inter_request_idle_s=0,
                  total_timeout_s=6000,
                  request_policy={'mode':'functional-quality','attempts':1,
                                  'max_tokens':3072,'temperature':0,'seed':42,
                                  'reasoning_effort':'medium',
                                  'per_request_timeout_s':600})
    for key in ('dynamic_cache_min_common','dynamic_cache_max_lost',
                'prompt_token_ranges','record_monotonic_request_markers'):
        config.pop(key, None)
    protocol.pop('trace', None)
    protocol['schema_version'] = 'c126-protocol-v1'
    protocol['protocol_id'] = RUN_ID + '-v1'
    protocol['expected_request_ids'] = ids
    protocol['identity'].update(config_sha256=server.digest(config),
                                workload_sha256=sha256(base.REPO/'workloads/c38_quality12.json'),
                                input_sha256={'workloads/c38_quality12.json':
                                              sha256(base.REPO/'workloads/c38_quality12.json')})
    parent = protocol.pop('c97')
    protocol['c126'] = {'model_stat':parent['model_stat'],
                        'backend_tree':parent['backend_tree'],
                        'runner_sha256':sha256(__file__),
                        'grader_sha256':sha256(base.REPO/'tools/c38_quality_grade.py'),
                        'prior_c40_p12_receipt_sha256':sha256(base.REPO/'results/c40-quality-recovery-20260928T0528Z/c40-p12-receipt.json'),
                        'claim':'C75 candidate on the original C40 12-task fixture; no broad quality claim'}
    protocol['start_inventory'] = {'schema':'c120-start-inventory-v1',
                                   'duration_s':60,'max_age_s':3,
                                   'policy_sha256':sha256(root/'resource-policy.json')}
    validate_resource_protocol(protocol)
    return protocol, config


def budget():
    now = datetime.now(timezone.utc)
    wall = (EPOCH_START + timedelta(hours=12) - now).total_seconds()
    # Previous epoch checkpoint is a conservative upper estimate. C126 needs
    # 6000 s server + 60 s inventory + 600 s closure, within 8 h physical.
    prior = strict_json((base.REPO/'results/c125b-component-io-probe-20260929T1555Z/epoch-checkpoint.json').read_text())
    physical = prior['physical_remaining_lower_bound_s']
    reserve = 6000 + 60 + 600
    if min(wall, physical) < reserve:
        raise GateError('C126 epoch cannot admit full quality arm and closure')
    return {'schema':'c126-budget-admission-v1','utc':now.isoformat(),
            'wall_remaining_s':wall,'physical_remaining_lower_bound_s':physical,
            'reserved_s':reserve,'prior_checkpoint_sha256':sha256(base.REPO/'results/c125b-component-io-probe-20260929T1555Z/epoch-checkpoint.json')}


def freeze(root):
    if root.name != ROOT_NAME or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C126 fresh root/raw/protocols required')
    self_test()
    save_new(root/'budget-admission.json', budget())
    protocol, config = make(root)
    save_new(root/'protocols'/f'{RUN_ID}.json', protocol)
    save_new(root/f'{RUN_ID}-config.json', config)
    save_new(root/'preflight.json', {'schema':'c126-freeze-v1','status':'FROZEN_NOT_MEASURED',
        'utc':datetime.now(timezone.utc).isoformat(),
        'files':{name:sha256(root/name) for name in
                 ('snapshot.json','resource-policy.json','session-input.json',
                  f'protocols/{RUN_ID}.json',f'{RUN_ID}-config.json')},
        'run_id':RUN_ID,'quality_workload_sha256':sha256(base.REPO/'workloads/c38_quality12.json'),
        'grader_sha256':sha256(base.REPO/'tools/c38_quality_grade.py')})


def frozen(root):
    pre = strict_json((root/'preflight.json').read_text())
    if pre['status'] != 'FROZEN_NOT_MEASURED' or pre['run_id'] != RUN_ID:
        raise GateError('C126 freeze status/identity invalid')
    if any(sha256(root/name) != expected for name, expected in pre['files'].items()):
        raise GateError('C126 frozen file changed')
    if sha256(base.REPO/'workloads/c38_quality12.json') != pre['quality_workload_sha256'] or \
       sha256(base.REPO/'tools/c38_quality_grade.py') != pre['grader_sha256']:
        raise GateError('C126 quality fixture/grader changed')
    protocol, config = make(root)
    if protocol != strict_json((root/'protocols'/f'{RUN_ID}.json').read_text()) or \
       config != strict_json((root/f'{RUN_ID}-config.json').read_text()):
        raise GateError('C126 source/config changed')
    return protocol, config


def validate(root, protocol, config, raw):
    samples = [strict_json(line) for line in
               (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    maxima = validate_receipt(protocol, config, raw, samples, root,
                              run_id=RUN_ID,protocol_filename=f'protocols/{RUN_ID}.json',
                              expected_results=12)
    ids = strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())
    if list(ids) != protocol['expected_request_ids'] or \
       [x['id'] for x in raw['results']] != protocol['expected_request_ids']:
        raise GateError('C126 task/tokenization identity invalid')
    results = []
    for item in raw['results']:
        usage, stream = item.get('usage'), item.get('stream_metrics')
        if item.get('finish_reason') != 'stop' or not stream or \
           stream.get('done_observed') is not True or \
           usage.get('prompt_tokens') != len(ids[item['id']]) or \
           not 0 < usage.get('completion_tokens', 0) < 3072:
            raise GateError('C126 incomplete task/output/usage')
        detail = grade(item['id'], item['message'].get('content'))
        if detail['status'] == 'VALIDATOR_ENV_ERROR':
            raise GateError('C126 validator isolation unavailable')
        results.append({'id':item['id'],'category':item['category'],
                        'status':detail['status'],'detail':detail,
                        'first_final_content_s':stream.get('first_final_content_chunk_s'),
                        'completion_tokens':usage['completion_tokens'],
                        'message_sha256':server.digest(item['message'])})
    return maxima, results


def run(root, commit):
    started = datetime.now(timezone.utc)
    launched = False; raw = None; inventory = None; maxima = None; results = None; failure = None
    try:
        budget()
        if base.git('rev-parse','HEAD') != commit or base.git('status','--porcelain') or \
           relevant_environment(os.environ):
            raise GateError('C126 measurement HEAD/worktree/environment not frozen')
        scope = server.cgroup_state()
        if not scope or scope['memory_max'] != CAP or scope['swap_max'] != 0:
            raise GateError('C126 cgroup E18/zero-swap invalid')
        protocol, config = frozen(root)
        no_other_model()
        policy = strict_json((root/'resource-policy.json').read_text())
        power = {key:policy['power'][key] for key in ('source','profile')}
        inventory = collect(root,RUN_ID,policy=policy,cap_bytes=CAP,
                            expected_power=power,duration_s=60)
        save_new(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json',inventory)
        require_inventory(root,RUN_ID,inventory,policy=policy,cap_bytes=CAP,
                          expected_power=power,duration_s=60)
        args = SimpleNamespace(run_id=RUN_ID,protocol=root/'protocols'/f'{RUN_ID}.json',
                               suite='c126quality',model='target120b')
        code = server.run(args,protocol,config,tasks(),MODEL)
        launched = (root/'raw'/f'{RUN_ID}.launch.json').is_file()
        raw = strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        maxima, results = validate(root,protocol,config,raw)
        if code != 0:
            raise GateError('C126 server runner returned failure')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
        launched = (root/'raw'/f'{RUN_ID}.launch.json').is_file()
    if raw is None and (root/'raw'/f'{RUN_ID}.json').is_file():
        raw = strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
    status = ('PASS_QUALITY_12_OF_12' if failure is None and
              all(x['status']=='PASS' for x in results) else
              'QUALITY_NO_LOSS_FAIL' if failure is None else
              'FAIL_RESOURCES_OR_EVIDENCE' if launched else 'FAIL_HARNESS_PREMODEL')
    receipt = {'schema':'c126-quality-receipt-v1','run_id':RUN_ID,
               'measurement_commit':commit,'started_utc':started.isoformat(),
               'ended_utc':datetime.now(timezone.utc).isoformat(),
               'status':status,'reason':failure,'model_launch_observed':launched,
               'completed_requests':len(raw['results']) if raw else 0,
               'stop_reasons':raw.get('stop_reasons') if raw else None,
               'inventory_receipt_sha256':sha256(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json') if inventory else None,
               'raw_sha256':sha256(root/'raw'/f'{RUN_ID}.json') if raw else None,
               'maxima':maxima,'results':results,'default_changed':False}
    save_new(root/'raw'/f'{RUN_ID}.receipt.json',receipt)
    print(json.dumps({'status':status,'completed':receipt['completed_requests'],
                      'pass_count':sum(x['status']=='PASS' for x in results) if results else None,
                      'reason':failure},allow_nan=False))
    return 0 if status=='PASS_QUALITY_12_OF_12' else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('freeze','run'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    root=args.root.resolve()
    if args.mode=='freeze':
        freeze(root)
    else:
        if not args.measurement_commit:
            parser.error('run requires measurement commit')
        raise SystemExit(run(root,args.measurement_commit))


if __name__=='__main__':
    main()
