#!/usr/bin/env python3
"""Same-binary trace-off neutral arm for the C135 slots40 diagnostic trace."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from types import SimpleNamespace

import c135_slots40_trace as c135
import c122_decode_trace as parent
import c112_nominal_session_base as base
import c117_operational_nominal_server as validator
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL
from c17_thermal_recovery import no_other_model
from c118_start_inventory import collect, require_inventory
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import relevant_environment, sha256


REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = 'c136-slots40-trace-neutral-20260929T2205Z'
RUN_ID = 'c136-c75-slots40-neutral'
PRIOR = REPO / 'results/c135-slots40-warm153-trace-20260929T2205Z'
CAP = 18 * GIB


def save_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def budget():
    checkpoint = strict_json((REPO / 'results/c134b-slots40-boundary-20260929T2140Z/epoch-checkpoint.json').read_text())
    now = datetime.now(timezone.utc)
    wall = (datetime.fromisoformat('2026-09-29T13:31:15+00:00') +
            timedelta(hours=12) - now).total_seconds()
    first = strict_json((PRIOR / 'raw/c135-c75-slots40-warm153.receipt.json').read_text())
    a, b = datetime.fromisoformat(first['started_utc']), datetime.fromisoformat(first['ended_utc'])
    if first['status'] != 'PASS_DIAGNOSTIC_CAPTURE' or b < a:
        raise GateError('C135 capture not valid for neutrality')
    physical = checkpoint['physical_remaining_lower_bound_s'] - 120 - (b-a).total_seconds()
    reserve = 600 + 60 + 600 + 1200
    if min(wall, physical) < reserve:
        raise GateError('C136 neutrality and closure reserve not admitted')
    return {'schema': 'c136-budget-v1', 'utc': now.isoformat(),
            'c135_receipt_sha256': sha256(PRIOR / 'raw/c135-c75-slots40-warm153.receipt.json'),
            'physical_remaining_lower_bound_s': physical,
            'wall_remaining_s': wall, 'reserved_s': reserve}


def make(root):
    c135.configure()
    p, c = c135.make(root)
    c.pop('trace_trigger_request_id')
    c['explicit_env'] = {'TESY_CPU_WAVE_SKIP_PARKED': '1'}
    c['suite'] = 'c136neutral'
    p['schema_version'] = 'c136-protocol-v1'
    p['protocol_id'] = RUN_ID + '-v1'
    p['identity']['config_sha256'] = parent.server.digest(c)
    p.pop('c135')
    p['c136'] = {'run_id': RUN_ID, 'slots_per_layer': 40,
                 'instrumented_backend_source': c135.trace.BACKEND_SHA,
                 'trace_file_env': 'ABSENT', 'trace_trigger_env': 'ABSENT',
                 'runner_sha256': sha256(__file__),
                 'c135_trace_receipt_sha256': sha256(PRIOR / 'raw/c135-c75-slots40-warm153.receipt.json'),
                 'purpose': 'same-binary trace-off neutral timing and exact output comparison'}
    p['trace'] = {'request_marker_schema': 'c85-request-monotonic-v1'}
    validate_resource_protocol(p)
    return p, c


def freeze(root):
    if root.name != ROOT_NAME or not (root / 'raw').is_dir() or \
       not (root / 'protocols').is_dir():
        raise GateError('C136 new root/raw/protocols required')
    save_new(root / 'budget-admission.json', budget())
    p, c = make(root)
    save_new(root / 'protocols' / f'{RUN_ID}.json', p)
    save_new(root / f'{RUN_ID}-config.json', c)
    files = ('snapshot.json', 'resource-policy.json', 'session-input.json',
             'budget-admission.json', f'protocols/{RUN_ID}.json', f'{RUN_ID}-config.json')
    save_new(root / 'preflight.json', {'schema': 'c136-freeze-v1',
        'status': 'FROZEN_NOT_MEASURED', 'utc': datetime.now(timezone.utc).isoformat(),
        'files': {name: sha256(root/name) for name in files}})


def run(root, commit):
    started = datetime.now(timezone.utc)
    failure = None
    raw = None
    maxima = None
    inventory = None
    launched = False
    try:
        budget()
        if base.git('rev-parse', 'HEAD') != commit or base.git('status', '--porcelain') or \
           relevant_environment(os.environ):
            raise GateError('C136 measurement SHA/worktree/environment changed')
        scope = parent.server.cgroup_state()
        if not scope or scope['memory_max'] != CAP or scope['swap_max'] != 0:
            raise GateError('C136 E18 zero-swap scope absent')
        pre = strict_json((root / 'preflight.json').read_text())
        if pre['status'] != 'FROZEN_NOT_MEASURED' or \
           any(sha256(root/name) != digest for name, digest in pre['files'].items()):
            raise GateError('C136 frozen file mismatch')
        p, c = make(root)
        if p != strict_json((root/'protocols'/f'{RUN_ID}.json').read_text()) or \
           c != strict_json((root/f'{RUN_ID}-config.json').read_text()):
            raise GateError('C136 frozen effective profile changed')
        no_other_model()
        policy = strict_json((root/'resource-policy.json').read_text())
        power = {key: policy['power'][key] for key in ('source', 'profile')}
        inventory = collect(root, RUN_ID, policy=policy, cap_bytes=CAP,
                            expected_power=power, duration_s=60)
        save_new(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json', inventory)
        require_inventory(root, RUN_ID, inventory, policy=policy, cap_bytes=CAP,
                          expected_power=power, duration_s=60)
        args = SimpleNamespace(run_id=RUN_ID, protocol=root/'protocols'/f'{RUN_ID}.json',
                               suite='c136neutral', model='target120b')
        code = parent.server.run(args, p, c, base.tasks(root), MODEL)
        launched = (root/'raw'/f'{RUN_ID}.launch.json').is_file()
        raw = strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        maxima = validator.validate_run(root, (RUN_ID, 'candidate', 1), p, c, raw)
        if code != 0:
            raise GateError('C136 server runner exit failure')
        previous = strict_json((PRIOR/'raw/c135-c75-slots40-warm153.json').read_text())
        ids = strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())
        prior_ids = strict_json((PRIOR/'raw/c135-c75-slots40-warm153.tokenization.json').read_text())
        if ids != prior_ids or [(x['message'], x['usage']['completion_tokens'], x['finish_reason']) for x in raw['results']] != \
           [(x['message'], x['usage']['completion_tokens'], x['finish_reason']) for x in previous['results']]:
            raise GateError('C136 neutral input or output differs from C135')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
        launched = (root/'raw'/f'{RUN_ID}.launch.json').is_file()
    status = 'PASS_TRACE_OFF_NEUTRAL' if failure is None else \
             ('FAIL_RESOURCES_OR_EVIDENCE' if launched else 'FAIL_HARNESS_PREMODEL')
    receipt = {'schema': 'c136-neutral-receipt-v1', 'run_id': RUN_ID,
        'measurement_commit': commit, 'status': status, 'reason': failure,
        'started_utc': started.isoformat(), 'ended_utc': datetime.now(timezone.utc).isoformat(),
        'model_launch_observed': launched,
        'inventory_receipt_sha256': sha256(root/'raw'/f'{RUN_ID}.start-inventory.receipt.json') if inventory else None,
        'raw_sha256': sha256(root/'raw'/f'{RUN_ID}.json') if raw else None,
        'maxima': maxima, 'default_changed': False}
    save_new(root/'raw'/f'{RUN_ID}.receipt.json', receipt)
    print(json.dumps({'status': status, 'reason': failure}))
    return 0 if failure is None else 1


if __name__ == '__main__':
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
