#!/usr/bin/env python3
"""Two alternating C35/C75 fresh-process nominal128 actual-history server pairs."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path
import re
import time
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL, validate_receipt
from c85_request_markers import validate as validate_markers
from c17_thermal_recovery import no_other_model
from host_resource_policy import GIB, validate_resource_protocol, live_power
from run_bounded import relevant_environment, sha256
import c112_nominal_session_base as base

CAP = 18 * GIB
ORDER = (('c112-p1-control', 'control', 1),
         ('c112-p1-candidate', 'candidate', 1),
         ('c112-p2-candidate', 'candidate', 2),
         ('c112-p2-control', 'control', 2))
ROOT_NAME = 'c112-nominal-server-20260929T1015Z'
EPOCH_LEDGER=base.REPO/'results/c108-trace-errata-20260929T0805Z/epoch-ledger.json'
WORST_CASE_S=4*600+2*300+2*60+600


def budget_admission():
    ledger=strict_json(EPOCH_LEDGER.read_text())
    now=datetime.now(timezone.utc)
    deadline=datetime.fromisoformat(ledger['epoch_start_conservative_utc'])+timedelta(
        seconds=ledger['limits_s']['wall'])
    physical=ledger['physical_remaining_lower_bound_s']-(now-datetime.fromisoformat(ledger['now_utc'])).total_seconds()
    wall=(deadline-now).total_seconds()
    row={'schema':'c112-budget-admission-v1','utc':now.isoformat(),
         'epoch_ledger_sha256':sha256(EPOCH_LEDGER),'worst_case_s':WORST_CASE_S,
         'wall_remaining_s':wall,'physical_remaining_lower_bound_s':physical,
         'method':'C108 upper bound; every subsequent wall second charged to physical'}
    if min(wall,physical)<WORST_CASE_S:
        raise GateError('C112 epoch cannot admit two pairs and closure')
    return row


def save_new(path, obj):
    with Path(path).open('x') as out:
        json.dump(obj, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def policy(root):
    return {
        'schema': 'c112-screen-policy-v1', 'status': 'FROZEN_BEFORE_MODEL',
        'objective': 'screen C35/C75 ON on nominal128 actual-assistant-history increment and first final content',
        'alternative': 'C111 teacher-forced gain does not transfer to server final-content latency; C100 decode regression persists',
        'order': [row[0] for row in ORDER], 'pairs': 2,
        'primary': 'warm first_final_content_s',
        'protected': ['warm decode_s','cold decode_s','cold first_final_content_s','cold prefill_s','answer and prefix correctness'],
        'gain_formula': '100*(control-candidate)/control, positive denominator',
        'screen_go': 'median paired primary gain >=5%, both pairs positive; warm/cold decode median gains >=-5%; all identity/output/resource gates pass',
        'start': {'mode': 'CAUSAL_AB_OPERATIONAL_MATCHED', 'within_pair_cpu_c': 3,
                  'within_pair_gpu_c': 3, 'within_pair_nvme_c': 2,
                  'maximum_wait_s': 300, 'sample_interval_s': 1,
                  'on_mismatch': 'CLOSE_FAMILY_NO_MODEL; preserve partial observations'},
        'resource_cap_bytes': CAP, 'scope_memory_swap_max_bytes': 0,
        'input_sha256': sha256(root/'session-input.json'),
        'prior_c111_decision_sha256': sha256(base.REPO/'results/c111-long-toggle-20260929T0930Z/decision.json'),
        'base_harness_sha256': sha256(base.__file__),
        'runner_sha256': sha256(__file__),
        'limitations': ['synthetic two-turn history; not M3 diverse or M4 quality',
                        'two screening pairs do not certify p95 or broad quality',
                        'page cache uncontrolled; O_DIRECT configured for expert I/O'],
        'default_changed': False,
    }


def make(root, spec):
    run_id, arm, pair = spec
    protocol, config = base.make(root, arm)
    config['suite'] = 'c112nominal'
    protocol['schema_version'] = 'c112-protocol-v1'
    protocol['protocol_id'] = run_id+'-v1'
    protocol['identity']['config_sha256'] = server.digest(config)
    old = protocol.pop('c97')
    protocol['c112'] = {'run_id':run_id, 'arm':arm, 'pair':pair,
                       'order_index':ORDER.index(spec)+1,
                       'model_stat':old['model_stat'],
                       'backend_tree':old['backend_tree'],
                       'base_harness_sha256':sha256(base.__file__),
                       'runner_sha256':sha256(__file__),
                       'confirm_policy_sha256':sha256(root/'confirm-policy.json'),
                       'claim':'two-pair nominal128 server screen; no M3/M4 promotion'}
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if root.name != ROOT_NAME or not root.is_dir() or not (root/'raw').is_dir() or \
       not (root/'protocols').is_dir():
        raise GateError('C112 new root/raw/protocols required')
    budget=budget_admission()
    save_new(root/'confirm-policy.json', policy(root))
    save_new(root/'budget-admission.json',budget)
    for spec in ORDER:
        p, c = make(root, spec)
        save_new(root/'protocols'/f'{spec[0]}.json', p)
        save_new(root/f'{spec[0]}-config.json', c)
    save_new(root/'preflight.json', {
        'schema':'c112-freeze-v1', 'utc':datetime.now(timezone.utc).isoformat(),
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'resource_policy_sha256':sha256(root/'resource-policy.json'),
        'input_sha256':sha256(root/'session-input.json'),
        'confirm_policy_sha256':sha256(root/'confirm-policy.json'),
        'protocol_sha256':{spec[0]:sha256(root/'protocols'/f'{spec[0]}.json') for spec in ORDER},
        'config_sha256':{spec[0]:sha256(root/f'{spec[0]}-config.json') for spec in ORDER},
        'status':'FROZEN_NOT_MEASURED'})


def thermal_match(anchor, current, sensor):
    if type(anchor) is not dict or type(current) is not dict or \
       type(sensor) is not str or not sensor:
        raise GateError('C112 invalid start observation')
    try:
        a = (anchor['thermal']['cpu_tctl_c'], anchor['gpu']['temperature_c'],
             anchor['thermal']['nvme_composite_by_sensor'][sensor])
        b = (current['thermal']['cpu_tctl_c'], current['gpu']['temperature_c'],
             current['thermal']['nvme_composite_by_sensor'][sensor])
    except (KeyError, TypeError) as exc:
        raise GateError('C112 start sensor missing') from exc
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in a+b):
        raise GateError('C112 start sensor nonfinite')
    return all(abs(x-y) <= tolerance for x,y,tolerance in zip(a,b,(3,3,2)))


def matched_start(root, spec, protocol):
    run_id, arm, pair = spec
    if spec in (ORDER[0], ORDER[2]):
        return {'status':'FIRST_ARM_ANCHOR_FROM_RUNNER_PREFLIGHT', 'duration_s':0}
    first_run_id = ORDER[(pair-1)*2][0]
    first_receipt = strict_json((root/'raw'/f'{first_run_id}.receipt.json').read_text())
    if first_receipt.get('status') != 'PASS_SCREEN_ARM_TESTED_SCOPE':
        raise GateError('C112 first arm of pair did not pass')
    anchor = strict_json((root/'raw'/f'{first_run_id}.preflight.json').read_text())['resource_start_observation']
    sensor = protocol['resources']['nvme'][0]['sensor']
    path = root/'raw'/f'{run_id}.start-match.jsonl'
    started = time.monotonic()
    with path.open('x') as out:
        while True:
            no_other_model()
            observed = {'thermal':server.thermal_state(prospective=True),
                        'gpu':server.gpu_state(prospective=True),
                        'power':live_power()}
            elapsed = time.monotonic()-started
            out.write(json.dumps({'elapsed_s':elapsed, 'observation':observed},allow_nan=False)+'\n')
            out.flush()
            if observed['power']['source'] != anchor['power']['source'] or \
               observed['power']['profile'] != anchor['power']['profile']:
                raise GateError('C112 AC/performance source changed during match')
            if thermal_match(anchor, observed, sensor):
                return {'status':'PASS_MATCHED_START', 'duration_s':elapsed,
                        'anchor':anchor, 'matched':observed,
                        'series_sha256':sha256(path)}
            if elapsed >= 300:
                raise GateError('C112 matched-start window exhausted')
            time.sleep(max(0, 1-(time.monotonic()-started-elapsed)))


def validate_run(root, spec, protocol, config, raw):
    run_id = spec[0]
    samples = [strict_json(line) for line in
               (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
    maxima = validate_receipt(protocol,config,raw,samples,root,
                              run_id=run_id,protocol_filename=f'protocols/{run_id}.json',
                              expected_results=2)
    ids = strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
    if list(ids) != list(base.REQUESTS) or \
       validate_markers(root/'raw'/f'{run_id}.request-markers.jsonl',
                        run_id,base.REQUESTS,raw['results'])['status'] != 'PASS':
        raise GateError('C112 tokenization/markers incomplete')
    for item in raw['results']:
        stream,usage = item.get('stream_metrics'),item.get('usage')
        if item.get('finish_reason') != 'stop' or \
           type(stream) is not dict or stream.get('done_observed') is not True or \
           type(stream.get('first_final_content_chunk_s')) not in (int,float) or \
           not math.isfinite(stream['first_final_content_chunk_s']) or \
           type(usage) is not dict or usage.get('prompt_tokens') != len(ids[item['id']]) or \
           not 0 < usage.get('completion_tokens',0) < base.input_row(root)['max_tokens'] or \
           not item['message'].get('content'):
            raise GateError('C112 final content/usage/stream incomplete')
    first, second = raw['results']
    first_text=first['message']['content'].strip()
    if re.fullmatch(r'[0-9]{5}',first_text) is None or \
       second['message']['content'].strip()!=first_text:
        raise GateError('C112 actual assistant-history answer differs')
    prior_ids,current_ids=ids[base.REQUESTS[0]],ids[base.REQUESTS[1]]
    common=next((i for i,(left,right) in enumerate(zip(prior_ids,current_ids))
                 if left!=right),min(len(prior_ids),len(current_ids)))
    new_ids=len(current_ids)-common
    cache_n=second['timings']['cache_n']
    bound=min(len(current_ids),common+first['usage']['completion_tokens'])
    if common<1900 or len(prior_ids)-common>32 or not 120<=new_ids<=190 or \
       type(cache_n) is not int or not common-32<=cache_n<=bound or \
       second['timings']['prompt_n']+cache_n!=len(current_ids):
        raise GateError('C112 official nominal increment/prefix cache outside frozen bounds')
    if os.stat(MODEL).st_mtime_ns != protocol['c112']['model_stat']['mtime_ns']:
        raise GateError('C112 model stat changed')
    return maxima


def run(root, spec, commit):
    budget_admission()
    if base.git('rev-parse','HEAD') != commit or base.git('status','--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C112 measurement commit/worktree/environment changed')
    run_id = spec[0]
    protocol,config = make(root,spec)
    pre = strict_json((root/'preflight.json').read_text())
    if policy(root) != strict_json((root/'confirm-policy.json').read_text()) or \
       strict_json((root/'protocols'/f'{run_id}.json').read_text()) != protocol or \
       strict_json((root/f'{run_id}-config.json').read_text()) != config or \
       any(sha256(root/name) != expected for name,expected in
           [('snapshot.json',pre['snapshot_sha256']),
            ('resource-policy.json',pre['resource_policy_sha256']),
            ('session-input.json',pre['input_sha256']),
            ('confirm-policy.json',pre['confirm_policy_sha256']),
            (f'protocols/{run_id}.json',pre['protocol_sha256'][run_id]),
            (f'{run_id}-config.json',pre['config_sha256'][run_id])]):
        raise GateError('C112 frozen protocol/config/input changed')
    for prior in ORDER[:ORDER.index(spec)]:
        if strict_json((root/'raw'/f'{prior[0]}.receipt.json').read_text())['status'] != 'PASS_SCREEN_ARM_TESTED_SCOPE':
            raise GateError('C112 earlier arm failed; family closed')
    failure = None
    raw = None
    maxima = None
    match = None
    try:
        no_other_model()
        available = server.mem_available()
        if available is None or available < CAP+protocol['resources']['memory']['reserve_bytes']:
            raise GateError('C112 E18 host reserve not admitted')
        match = matched_start(root,spec,protocol)
        no_other_model()
        args = SimpleNamespace(run_id=run_id, protocol=root/'protocols'/f'{run_id}.json',
                               suite='c112nominal', model='target120b')
        code = server.run(args,protocol,config,base.tasks(root),MODEL)
        raw = strict_json((root/'raw'/f'{run_id}.json').read_text())
        maxima = validate_run(root,spec,protocol,config,raw)
        if code != 0:
            raise GateError('C112 server runner exit failure')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    receipt = {'schema':'c112-arm-receipt-v1','run_id':run_id,'arm':spec[1],
               'pair':spec[2],'measurement_commit':commit,
               'status':'PASS_SCREEN_ARM_TESTED_SCOPE' if failure is None else 'FAIL_RESOURCES_OR_EVIDENCE',
               'reason':failure,'matched_start':match,
               'completed_requests':len(raw['results']) if raw else 0,
               'stop_reasons':raw.get('stop_reasons') if raw else None,
               'maxima':maxima,
               'raw_sha256':sha256(root/'raw'/f'{run_id}.json') if raw else None,
               'default_changed':False}
    save_new(root/'raw'/f'{run_id}.receipt.json',receipt)
    print(json.dumps(receipt,allow_nan=False))
    return 0 if failure is None else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('freeze','run'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--run-id',choices=[x[0] for x in ORDER])
    parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.mode=='freeze':freeze(root)
    else:
        if not args.run_id or not args.measurement_commit:
            parser.error('run requires run-id and measurement commit')
        raise SystemExit(run(root,next(x for x in ORDER if x[0]==args.run_id),args.measurement_commit))
