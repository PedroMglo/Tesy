#!/usr/bin/env python3
"""One bounded C75 ON warm153 server trace, using the admitted C121 call plan."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL
from c17_thermal_recovery import no_other_model
from c118_start_inventory import collect, require_inventory
from c122_trace_validate import validate as validate_trace
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import backend_library_hashes, relevant_environment, sha256
import c112_nominal_session_base as base
import c117_operational_nominal_server as previous

REPO = Path(__file__).resolve().parents[1]
BACKEND = Path('/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming-c122-trace')
BUILD = BACKEND / 'build-c122-cuda-v2/bin'
BACKEND_SHA = 'ba058e62c33f6e1c6d8581c4685d9abb64542027'
SOURCE = REPO / 'results/c121-nominal153-20260929T1350Z'
ROOT_NAME = 'c122-warm153-decode-trace-20260929T1433Z'
RUN_ID = 'c122-c75-warm153'
CAP = 18 * GIB


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def git(*args):
    return base.git(*args)


def make(root):
    if git('-C', BACKEND, 'rev-parse', 'HEAD') != BACKEND_SHA or \
       git('-C', BACKEND, 'status', '--porcelain'):
        raise GateError('C122 backend source changed')
    binary = BUILD / 'llama-server'
    if not binary.is_file():
        raise GateError('C122 server binary missing')
    old_config = strict_json((SOURCE / 'c121-p1-candidate-config.json').read_text())
    old_protocol = strict_json((SOURCE / 'protocols/c121-p1-candidate.json').read_text())
    config = dict(old_config)
    config['suite'] = 'c122trace'
    config['output_root'] = str((root / 'raw').resolve())
    config['backend_root'] = str(BACKEND)
    config['server_command'] = [str(binary)] + old_config['server_command'][1:]
    config['trace_trigger_request_id'] = 'c112-repeat'
    trace_file = (root / 'raw' / f'{RUN_ID}.expert.trace').resolve()
    trigger_file = (root / 'raw' / f'{RUN_ID}.trace-trigger.json').resolve()
    config['explicit_env'] = {'TESY_CPU_WAVE_SKIP_PARKED':'1',
        'TESY_C84_EXPERT_TRACE_FILE':str(trace_file),
        'TESY_C122_TRACE_TRIGGER_FILE':str(trigger_file)}
    libs = backend_library_hashes(str(binary), BACKEND)
    if not libs:
        raise GateError('C122 mapped backend libraries unavailable')
    protocol = dict(old_protocol)
    protocol['schema_version'] = 'c122-protocol-v1'
    protocol['campaign_id'] = root.name
    protocol['protocol_id'] = RUN_ID + '-v1'
    protocol['identity'] = dict(old_protocol['identity'])
    protocol['identity'].update(backend_sha=git('-C',BACKEND,'rev-parse','HEAD'),
        binary_sha256=sha256(binary), library_sha256=libs,
        config_sha256=server.digest(config))
    protocol['trace'] = {'request_marker_schema':'c85-request-monotonic-v1',
                         'expert_trace_schema':'c122-expert-decode-v1',
                         'trigger_request_id':'c112-repeat',
                         'trace_file':str(trace_file), 'max_trace_bytes':64*2**20,
                         'max_capture_bytes':256*2**20}
    protocol['c120'] = {'model_stat':old_protocol['c120']['model_stat']}
    protocol['c122'] = {'run_id':RUN_ID,'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
        'backend_source_commit':git('-C',BACKEND,'rev-parse','HEAD'),
        'original_candidate_measurement_commit':
          '3abc0071d26d87f5ea8cabca19b2d7c3ae388f60',
        'source_c121_decision_sha256':sha256(SOURCE/'decision.json'),
        'intervention':'diagnostic instrumentation only; same placement/routing/compute',
        'claim_limit':'trace timing is diagnostic, not production performance'}
    protocol['start_inventory']['policy_sha256'] = sha256(root/'resource-policy.json')
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if root.name != ROOT_NAME or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C122 new root/raw/protocols required')
    if strict_json((SOURCE/'decision.json').read_text())['status'] != 'SCREEN_GO_OPERATIONAL_NOMINAL153':
        raise GateError('C121 admitted screen required')
    for name in ('snapshot.json','resource-policy.json','session-input.json'):
        (root/name).write_bytes((SOURCE/name).read_bytes())
    p,c = make(root)
    save_new(root/'protocols'/f'{RUN_ID}.json',p)
    save_new(root/f'{RUN_ID}-config.json',c)
    save_new(root/'preflight.json', {'schema':'c122-freeze-v1',
        'utc':datetime.now(timezone.utc).isoformat(),
        'protocol_sha256':sha256(root/'protocols'/f'{RUN_ID}.json'),
        'config_sha256':sha256(root/f'{RUN_ID}-config.json'),
        'policy_sha256':sha256(root/'resource-policy.json'),
        'input_sha256':sha256(root/'session-input.json'),
        'backend_source_commit':git('-C',BACKEND,'rev-parse','HEAD'),
        'status':'FROZEN_NOT_MEASURED'})


def run(root, commit):
    started = datetime.now(timezone.utc)
    failure = None
    launched = False
    inv = None
    raw = None
    maxima = None
    trace_summary = None
    try:
        if git('rev-parse','HEAD') != commit or git('status','--porcelain') or \
           relevant_environment(os.environ):
            raise GateError('C122 measurement SHA/worktree/environment changed')
        scope = server.cgroup_state()
        if not scope or scope['memory_max'] != CAP or scope['swap_max'] != 0:
            raise GateError('C122 E18 zero-swap scope absent')
        no_other_model()
        p,c = make(root)
        frozen = strict_json((root/'preflight.json').read_text())
        files = ((root/'protocols'/f'{RUN_ID}.json',p,'protocol_sha256'),
                 (root/f'{RUN_ID}-config.json',c,'config_sha256'))
        for path, expected, key in files:
            if strict_json(path.read_text()) != expected or sha256(path) != frozen[key]:
                raise GateError('C122 frozen profile changed')
        if sha256(root/'resource-policy.json') != frozen['policy_sha256'] or \
           sha256(root/'session-input.json') != frozen['input_sha256']:
            raise GateError('C122 frozen policy/input changed')
        policy = strict_json((root/'resource-policy.json').read_text())
        power = {key:policy['power'][key] for key in ('source','profile')}
        inv = collect(root,RUN_ID,policy=policy,cap_bytes=CAP,
                      expected_power=power,duration_s=60)
        save_new(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json',inv)
        require_inventory(root,RUN_ID,inv,policy=policy,cap_bytes=CAP,
                          expected_power=power,duration_s=60)
        args = SimpleNamespace(run_id=RUN_ID,protocol=root/'protocols'/f'{RUN_ID}.json',
                               suite='c122trace',model='target120b')
        code = server.run(args,p,c,base.tasks(root),MODEL)
        launched = (root/'raw'/f'{RUN_ID}.launch.json').is_file()
        raw = strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        maxima = previous.validate_run(root,(RUN_ID,'candidate',1),p,c,raw)
        if code != 0:
            raise GateError('C122 server runner failed')
        trace_path = root/'raw'/f'{RUN_ID}.expert.trace'
        trace_summary = validate_trace(trace_path)
        trigger = strict_json((root/'raw'/f'{RUN_ID}.trace-trigger.json').read_text())
        if trigger['run_id'] != RUN_ID or trigger['request_id'] != 'c112-repeat' or \
           not trace_summary['calls']:
            raise GateError('C122 trigger/trace request mismatch')
        total_capture = sum(x.stat().st_size for x in (root/'raw').iterdir() if x.is_file())
        if total_capture > 256*2**20:
            raise GateError('C122 capture exceeds 256 MiB')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
        launched = (root/'raw'/f'{RUN_ID}.launch.json').is_file()
    receipt = {'schema':'c122-trace-receipt-v1','run_id':RUN_ID,
        'measurement_commit':commit,'started_utc':started.isoformat(),
        'ended_utc':datetime.now(timezone.utc).isoformat(),
        'status':'PASS_DIAGNOSTIC_CAPTURE' if failure is None else
                 ('FAIL_RESOURCES_OR_EVIDENCE' if launched else 'FAIL_HARNESS_PREMODEL'),
        'reason':failure,'model_launch_observed':launched,
        'inventory_receipt_sha256':sha256(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json') if inv else None,
        'raw_sha256':sha256(root/'raw'/f'{RUN_ID}.json') if raw else None,
        'trace_sha256':sha256(root/'raw'/f'{RUN_ID}.expert.trace') if (root/'raw'/f'{RUN_ID}.expert.trace').is_file() else None,
        'maxima':maxima,'trace':trace_summary,'default_changed':False}
    save_new(root/'raw'/f'{RUN_ID}.receipt.json',receipt)
    print(json.dumps({'status':receipt['status'],'reason':failure,
                      'trace_events':trace_summary['events'] if trace_summary else None}))
    return 0 if failure is None else 1


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path)
    ap.add_argument('--measurement-commit')
    a=ap.parse_args();root=a.root.resolve()
    if a.mode=='freeze': freeze(root)
    else:
        if not a.measurement_commit: ap.error('run needs full measurement commit')
        raise SystemExit(run(root,a.measurement_commit))
