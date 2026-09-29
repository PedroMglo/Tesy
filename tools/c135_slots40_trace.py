#!/usr/bin/env python3
"""One bounded diagnostic warm153 trace of the confirmed C75/slots40 profile."""

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

import c122_decode_trace as trace
import c112_nominal_session_base as base
from c2_gate import GateError, strict_json
from host_resource_policy import GIB, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, sha256


REPO = Path(__file__).resolve().parents[1]
BACKEND = trace.BACKEND
BUILD = BACKEND / 'build-c123-cuda/bin'
ROOT_NAME = 'c135-slots40-warm153-trace-20260929T2205Z'
RUN_ID = 'c135-c75-slots40-warm153'
PRIOR = REPO / 'results/c134b-slots40-boundary-20260929T2140Z/epoch-checkpoint.json'
REFERENCE = REPO / 'results/c129-slots40-confirm-20260929T1735Z'
CAP = 18 * GIB


def configure():
    trace.ROOT_NAME = ROOT_NAME
    trace.RUN_ID = RUN_ID
    trace.BUILD = BUILD
    trace.make = make
    base.BACKENDS['candidate'] = (BACKEND, 'build-c123-cuda', trace.BACKEND_SHA,
                                  {'TESY_CPU_WAVE_SKIP_PARKED': '1'})


def budget():
    prior = strict_json(PRIOR.read_text())
    now = datetime.now(timezone.utc)
    wall = (datetime.fromisoformat('2026-09-29T13:31:15+00:00') +
            timedelta(hours=12) - now).total_seconds()
    physical = prior['physical_remaining_lower_bound_s']
    reserve = 600 + 60 + 600 + 1800
    if min(wall, physical) < reserve:
        raise GateError('C135 trace and closure reserve not admitted')
    return {'schema': 'c135-budget-v1', 'utc': now.isoformat(),
            'prior_checkpoint_sha256': sha256(PRIOR),
            'physical_remaining_lower_bound_s': physical,
            'wall_remaining_s': wall, 'reserved_s': reserve,
            'model_limit_s': 600, 'trace_limit_bytes': 64 * 2**20,
            'capture_limit_bytes': 256 * 2**20}


def make(root):
    if base.git('-C', BACKEND, 'rev-parse', 'HEAD') != trace.BACKEND_SHA or \
       base.git('-C', BACKEND, 'status', '--porcelain'):
        raise GateError('C135 instrumented backend source changed')
    p, c = base.make(root, 'candidate')
    command = c['server_command']
    i = command.index('--moe-stream-cache') + 1
    if command[i] != '32s':
        raise GateError('C135 base profile is not slots32')
    command[i] = '40s'
    binary = BUILD / 'llama-server'
    if Path(command[0]) != binary:
        raise GateError('C135 instrumented binary mismatch')
    trace_file = (root / 'raw' / f'{RUN_ID}.expert.trace').resolve()
    trigger_file = (root / 'raw' / f'{RUN_ID}.trace-trigger.json').resolve()
    c.update(suite='c135trace', trace_trigger_request_id='c112-repeat')
    c['explicit_env'] = {'TESY_CPU_WAVE_SKIP_PARKED': '1',
                         'TESY_C84_EXPERT_TRACE_FILE': str(trace_file),
                         'TESY_C122_TRACE_TRIGGER_FILE': str(trigger_file)}
    p['schema_version'] = 'c135-protocol-v1'
    p['campaign_id'] = root.name
    p['protocol_id'] = RUN_ID + '-v1'
    p['identity'].update(config_sha256=trace.server.digest(c),
                         binary_sha256=sha256(binary),
                         library_sha256=backend_library_hashes(str(binary), BACKEND))
    old = p.pop('c97')
    p['c120'] = {'model_stat': old['model_stat']}
    p['c135'] = {'run_id': RUN_ID, 'backend_tree': old['backend_tree'],
                 'instrumented_backend_source': trace.BACKEND_SHA,
                 'slots_per_layer': 40, 'wave_skip_parked': True,
                 'runner_sha256': sha256(__file__),
                 'reference_c129_decision_sha256': sha256(REFERENCE / 'decision.json'),
                 'purpose': 'diagnostic residual decode waits after slots40; no timing promotion',
                 'neutrality_rule': 'same official input IDs, output text and token counts as C129 candidate; trace-on timing descriptive only'}
    policy = strict_json((root / 'resource-policy.json').read_text())
    p['resources'] = freeze_protocol_resource_limits(policy,
                                                     cgroup_memory_max_bytes=CAP)
    p['start_inventory'] = {'schema': 'c120-start-inventory-v1',
                            'duration_s': 60, 'max_age_s': 3,
                            'policy_sha256': sha256(root / 'resource-policy.json')}
    p['trace'] = {'request_marker_schema': 'c85-request-monotonic-v1',
                  'expert_trace_schema': 'c122-expert-decode-v1',
                  'trigger_request_id': 'c112-repeat',
                  'trace_file': str(trace_file),
                  'max_trace_bytes': 64 * 2**20,
                  'max_capture_bytes': 256 * 2**20}
    validate_resource_protocol(p)
    return p, c


def freeze(root):
    if root.name != ROOT_NAME or not (root / 'raw').is_dir() or \
       not (root / 'protocols').is_dir():
        raise GateError('C135 new root/raw/protocols required')
    trace.save_new(root / 'budget-admission.json', budget())
    p, c = make(root)
    trace.save_new(root / 'protocols' / f'{RUN_ID}.json', p)
    trace.save_new(root / f'{RUN_ID}-config.json', c)
    files = ['snapshot.json', 'resource-policy.json', 'session-input.json',
             'budget-admission.json', f'protocols/{RUN_ID}.json',
             f'{RUN_ID}-config.json']
    trace.save_new(root / 'preflight.json', {
        'schema': 'c135-freeze-v1', 'status': 'FROZEN_NOT_MEASURED',
        'utc': datetime.now(timezone.utc).isoformat(),
        'files': {name: sha256(root / name) for name in files},
        'protocol_sha256': sha256(root / 'protocols' / f'{RUN_ID}.json'),
        'config_sha256': sha256(root / f'{RUN_ID}-config.json'),
        'policy_sha256': sha256(root / 'resource-policy.json'),
        'input_sha256': sha256(root / 'session-input.json')})


def run(root, commit):
    budget()
    pre = strict_json((root / 'preflight.json').read_text())
    if pre['status'] != 'FROZEN_NOT_MEASURED' or \
       any(sha256(root / name) != digest for name, digest in pre['files'].items()):
        raise GateError('C135 frozen file mismatch')
    return trace.run(root, commit)


if __name__ == '__main__':
    configure()
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('freeze', 'run'))
    ap.add_argument('root', type=Path)
    ap.add_argument('--measurement-commit')
    a = ap.parse_args()
    root = a.root.resolve()
    if a.mode == 'freeze':
        freeze(root)
    else:
        if not a.measurement_commit:
            ap.error('run requires measurement commit')
        raise SystemExit(run(root, a.measurement_commit))
