#!/usr/bin/env python3
"""Two alternating C75 OFF/ON server pairs to diagnose C100 decode cost."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL, validate_receipt
from c85_request_markers import validate as validate_markers
from c17_thermal_recovery import no_other_model
from host_resource_policy import GIB, validate_resource_protocol, live_power
from run_bounded import relevant_environment, sha256
import c97_server_wave_bridge as base

CAP = 18 * GIB
ORDER = (('c103-p1-off', 'off', 1),
         ('c103-p1-on', 'on', 1),
         ('c103-p2-on', 'on', 2),
         ('c103-p2-off', 'off', 2))
ROOT_NAME = 'c103-server-wave-toggle-20260928T2254Z'


def save_new(path, obj):
    with Path(path).open('x') as out:
        json.dump(obj, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def preflight_identity(commit):
    if type(commit) is not str or len(commit) != 40 or \
       any(char not in '0123456789abcdef' for char in commit):
        raise GateError('C103 measurement commit must be a full 40-character SHA')
    if base.git('rev-parse','HEAD') != commit or base.git('status','--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C103 measurement commit/worktree/environment changed')


def policy(root):
    return {
        'schema': 'c103-toggle-policy-v1', 'status': 'FROZEN_BEFORE_MODEL',
        'objective': 'diagnose C100 decode regression by toggling wave skip OFF/ON in the same C75 binary on the same two-request workload',
        'alternative': 'the C100 decode regression arose from build differences or uncontrolled state rather than active wave skip',
        'order': [row[0] for row in ORDER], 'pairs': 2,
        'primary': ['cold decode_s', 'warm decode_s'],
        'diagnostic_rule': 'report both paired 100*(OFF-ON)/OFF gains for cold/warm decode and prefill, with same-profile full outputs and resources; two consistently negative decode gains implicate active skip in this workload but are not confirmation or promotion',
        'gain_formula': '100*(OFF-ON)/OFF, positive denominator',
        'start': {'mode': 'CAUSAL_AB_COLD_MATCHED', 'within_pair_cpu_c': 3,
                  'within_pair_gpu_c': 3, 'within_pair_nvme_c': 2,
                  'maximum_wait_s': 300, 'sample_interval_s': 1,
                  'on_mismatch': 'CLOSE_PAIR_NO_MODEL; new warm-regime identity if justified'},
        'resource_cap_bytes': CAP, 'scope_memory_swap_max_bytes': 0,
        'input_sha256': sha256(root/'session-input.json'),
        'prior_c100_decision_sha256': sha256(base.REPO/'results/c100-server-wave-confirm-20260928T2211Z/decision.json'),
        'base_harness_sha256': sha256(base.__file__),
        'runner_sha256': sha256(__file__),
        'limitations': ['synthetic two-turn history; not M3 diverse or M4 quality',
                        'two diagnostic pairs do not confirm a performance promotion',
                        'page cache uncontrolled; O_DIRECT configured for expert I/O'],
        'default_changed': False,
    }


def make(root, spec):
    run_id, arm, pair = spec
    protocol, config = base.make(root, 'candidate')
    config['explicit_env'] = {} if arm == 'off' else {'TESY_CPU_WAVE_SKIP_PARKED':'1'}
    config['suite'] = 'c103toggle'
    protocol['schema_version'] = 'c103-protocol-v1'
    protocol['protocol_id'] = run_id+'-v1'
    protocol['identity']['config_sha256'] = server.digest(config)
    old = protocol.pop('c97')
    protocol['c103'] = {'run_id':run_id, 'arm':arm, 'pair':pair,
                       'order_index':ORDER.index(spec)+1,
                       'model_stat':old['model_stat'],
                       'backend_tree':old['backend_tree'],
                       'base_harness_sha256':sha256(base.__file__),
                       'runner_sha256':sha256(__file__),
                       'toggle_policy_sha256':sha256(root/'toggle-policy.json'),
                       'claim':'same-binary OFF/ON diagnostic in this synthetic workload; no M3/M4 promotion'}
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if root.name != ROOT_NAME or not root.is_dir() or not (root/'raw').is_dir() or \
       not (root/'protocols').is_dir():
        raise GateError('C103 new root/raw/protocols required')
    save_new(root/'toggle-policy.json', policy(root))
    for spec in ORDER:
        p, c = make(root, spec)
        save_new(root/'protocols'/f'{spec[0]}.json', p)
        save_new(root/f'{spec[0]}-config.json', c)
    save_new(root/'preflight.json', {
        'schema':'c103-freeze-v1', 'utc':datetime.now(timezone.utc).isoformat(),
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'resource_policy_sha256':sha256(root/'resource-policy.json'),
        'input_sha256':sha256(root/'session-input.json'),
        'toggle_policy_sha256':sha256(root/'toggle-policy.json'),
        'protocol_sha256':{spec[0]:sha256(root/'protocols'/f'{spec[0]}.json') for spec in ORDER},
        'config_sha256':{spec[0]:sha256(root/f'{spec[0]}-config.json') for spec in ORDER},
        'status':'FROZEN_NOT_MEASURED'})


def thermal_match(anchor, current, sensor):
    if type(anchor) is not dict or type(current) is not dict or \
       type(sensor) is not str or not sensor:
        raise GateError('C103 invalid start observation')
    try:
        a = (anchor['thermal']['cpu_tctl_c'], anchor['gpu']['temperature_c'],
             anchor['thermal']['nvme_composite_by_sensor'][sensor])
        b = (current['thermal']['cpu_tctl_c'], current['gpu']['temperature_c'],
             current['thermal']['nvme_composite_by_sensor'][sensor])
    except (KeyError, TypeError) as exc:
        raise GateError('C103 start sensor missing') from exc
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in a+b):
        raise GateError('C103 start sensor nonfinite')
    return all(abs(x-y) <= tolerance for x,y,tolerance in zip(a,b,(3,3,2)))


def matched_start(root, spec, protocol):
    run_id, arm, pair = spec
    if spec in (ORDER[0], ORDER[2]):
        return {'status':'FIRST_ARM_ANCHOR_FROM_RUNNER_PREFLIGHT', 'duration_s':0}
    first_run_id = ORDER[(pair-1)*2][0]
    first_receipt = strict_json((root/'raw'/f'{first_run_id}.receipt.json').read_text())
    if first_receipt.get('status') != 'PASS_TOGGLE_ARM_TESTED_SCOPE':
        raise GateError('C103 first arm of pair did not pass')
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
                raise GateError('C103 AC/performance source changed during match')
            if thermal_match(anchor, observed, sensor):
                return {'status':'PASS_MATCHED_START', 'duration_s':elapsed,
                        'anchor':anchor, 'matched':observed,
                        'series_sha256':sha256(path)}
            if elapsed >= 300:
                raise GateError('C103 matched-start window exhausted')
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
        raise GateError('C103 tokenization/markers incomplete')
    for earlier, _, _ in ORDER[:ORDER.index(spec)]:
        previous = strict_json((root/'raw'/f'{earlier}.json').read_text())
        previous_ids = strict_json((root/'raw'/f'{earlier}.tokenization.json').read_text())
        if ids != previous_ids or \
           [item['message'] for item in raw['results']] != \
           [item['message'] for item in previous['results']]:
            raise GateError('C103 same-profile tokens or full assistant messages differ')
    for item in raw['results']:
        stream,usage = item.get('stream_metrics'),item.get('usage')
        if item.get('finish_reason') != 'stop' or \
           type(stream) is not dict or stream.get('done_observed') is not True or \
           type(stream.get('first_final_content_chunk_s')) not in (int,float) or \
           not math.isfinite(stream['first_final_content_chunk_s']) or \
           type(usage) is not dict or usage.get('prompt_tokens') != len(ids[item['id']]) or \
           not 0 < usage.get('completion_tokens',0) < base.input_row(root)['max_tokens'] or \
           not item['message'].get('content'):
            raise GateError('C103 final content/usage/stream incomplete')
    if os.stat(MODEL).st_mtime_ns != protocol['c103']['model_stat']['mtime_ns']:
        raise GateError('C103 model stat changed')
    return maxima


def run(root, spec, commit):
    preflight_identity(commit)
    run_id = spec[0]
    protocol,config = make(root,spec)
    pre = strict_json((root/'preflight.json').read_text())
    if policy(root) != strict_json((root/'toggle-policy.json').read_text()) or \
       strict_json((root/'protocols'/f'{run_id}.json').read_text()) != protocol or \
       strict_json((root/f'{run_id}-config.json').read_text()) != config or \
       any(sha256(root/name) != expected for name,expected in
           [('snapshot.json',pre['snapshot_sha256']),
            ('resource-policy.json',pre['resource_policy_sha256']),
            ('session-input.json',pre['input_sha256']),
            ('toggle-policy.json',pre['toggle_policy_sha256']),
            (f'protocols/{run_id}.json',pre['protocol_sha256'][run_id]),
            (f'{run_id}-config.json',pre['config_sha256'][run_id])]):
        raise GateError('C103 frozen protocol/config/input changed')
    for prior in ORDER[:ORDER.index(spec)]:
        if strict_json((root/'raw'/f'{prior[0]}.receipt.json').read_text())['status'] != 'PASS_TOGGLE_ARM_TESTED_SCOPE':
            raise GateError('C103 earlier arm failed; family closed')
    failure = None
    raw = None
    maxima = None
    match = None
    try:
        no_other_model()
        available = server.mem_available()
        if available is None or available < CAP+protocol['resources']['memory']['reserve_bytes']:
            raise GateError('C103 E18 host reserve not admitted')
        match = matched_start(root,spec,protocol)
        no_other_model()
        args = SimpleNamespace(run_id=run_id, protocol=root/'protocols'/f'{run_id}.json',
                               suite='c103toggle', model='target120b')
        code = server.run(args,protocol,config,base.tasks(root),MODEL)
        raw = strict_json((root/'raw'/f'{run_id}.json').read_text())
        maxima = validate_run(root,spec,protocol,config,raw)
        if code != 0:
            raise GateError('C103 server runner exit failure')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    receipt = {'schema':'c103-arm-receipt-v1','run_id':run_id,'arm':spec[1],
               'pair':spec[2],'measurement_commit':commit,
               'status':'PASS_TOGGLE_ARM_TESTED_SCOPE' if failure is None else 'FAIL_RESOURCES_OR_EVIDENCE',
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
