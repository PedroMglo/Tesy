#!/usr/bin/env python3
"""One bounded C75 8K server load/forward canary after C90 E18 admission."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import validate_receipt
from c17_thermal_recovery import no_other_model
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, relevant_environment, sha256
import c58_resource_canary as prior

REPO = Path(__file__).resolve().parents[1]
BACKEND = Path('/tmp/tesy-c75-backend-20260928')
BINARY = BACKEND / 'build-c75-cuda/bin/llama-server'
MODEL = prior.MODEL
CAP = 18 * GIB
PORT = 18391
RUN_ID = 'c91-p12-c75-e18-canary01'
TASK = {'id': 'c91-synthetic-canary01', 'category': 'synthetic-canary',
        'prompt': 'Reply with OK.'}


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def make(root):
    old, _, model_stat = prior.original()
    snapshot = strict_json((root/'snapshot.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    source = REPO/'results/c90-e18-capacity-preflight-20260928T2035Z'
    if sha256(root/'snapshot.json') != sha256(source/'snapshot.json') or \
       sha256(root/'resource-policy.json') != sha256(source/'resource-policy.json') or \
       derive_policy(snapshot=snapshot) != policy or \
       policy['memory']['cap_max_bytes'] < CAP:
        raise GateError('C90 inventory/policy does not admit E18')
    if git('-C', BACKEND, 'rev-parse', 'HEAD') != '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5' or \
       git('-C', BACKEND, 'status', '--porcelain'):
        raise GateError('C75 source changed')
    libraries = backend_library_hashes(str(BINARY), BACKEND)
    binary_hash = sha256(BINARY)
    command = list(old['config']['server_command'])
    command[0] = str(BINARY)
    command[command.index('--port')+1] = str(PORT)
    config = {'server_command': command,
              'explicit_env': {'TESY_CPU_WAVE_SKIP_PARKED': '1'},
              'suite': 'c91canary', 'task_ids': [TASK['id']],
              'request_policy': {'mode': 'synthetic-short-canary', 'attempts': 1,
                                 'max_tokens': 1, 'temperature': 0, 'seed': 42,
                                 'per_request_timeout_s': 180},
              'total_timeout_s': 300,
              'output_root': str((root/'raw').resolve()),
              'backend_root': str(BACKEND), 'n_ctx': 8192,
              'stream_requests': False}
    identity = dict(old['protocol']['identity'])
    identity.update(backend_sha=git('-C', BACKEND, 'rev-parse', 'HEAD'),
                    binary_sha256=binary_hash, library_sha256=libraries,
                    config_sha256=server.digest(config),
                    workload_sha256=server.digest([TASK]),
                    input_sha256={TASK['id']: server.digest(TASK)})
    protocol = {'schema_version': 'c91-protocol-v1',
                'campaign_id': root.name, 'protocol_id': 'c91-c75-e18-server-canary-v1',
                'identity': identity, 'expected_request_ids': [TASK['id']],
                'limits': {'max_gap_s': 3, 'boundary_s': 2},
                'resources': freeze_protocol_resource_limits(policy, cgroup_memory_max_bytes=CAP),
                'c91': {'model_stat': model_stat,
                        'backend_tree': git('-C', BACKEND, 'rev-parse', 'HEAD^{tree}'),
                        'runner_sha256': sha256(__file__),
                        'C90_snapshot_sha256': sha256(source/'snapshot.json'),
                        'C90_policy_sha256': sha256(source/'resource-policy.json'),
                        'claim': 'one 8K server load and one-token forward canary only'}}
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new root/raw required')
    protocol, config = make(root)
    save_new(root/'protocol.json', protocol)
    save_new(root/'config.json', config)
    save_new(root/'preflight.json', {
        'schema': 'c91-freeze-preflight-v1',
        'utc': datetime.now(timezone.utc).isoformat(),
        'C90_snapshot_sha256': sha256(root/'snapshot.json'),
        'C90_policy_sha256': sha256(root/'resource-policy.json'),
        'protocol_sha256': sha256(root/'protocol.json'),
        'config_sha256': sha256(root/'config.json'),
        'binary_sha256': protocol['identity']['binary_sha256'],
        'model_stat': protocol['c91']['model_stat'],
        'selected_cap_bytes': CAP, 'run_id': RUN_ID,
        'status': 'FROZEN_NOT_MEASURED'})


def port_available():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', PORT))


def run(root, commit):
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    protocol, config = make(root)
    if strict_json((root/'protocol.json').read_text()) != protocol or \
       strict_json((root/'config.json').read_text()) != config:
        raise GateError('frozen C91 protocol/config differs')
    frozen = strict_json((root/'preflight.json').read_text())
    for key, path in (('protocol_sha256', 'protocol.json'),
                      ('config_sha256', 'config.json'),
                      ('C90_snapshot_sha256', 'snapshot.json'),
                      ('C90_policy_sha256', 'resource-policy.json')):
        if frozen[key] != sha256(root/path):
            raise GateError(f'frozen C91 {key} changed')
    stage = 'PRELAUNCH'
    raw = None
    maxima = None
    failure = None
    try:
        available = prior.server.mem_available_bytes() if hasattr(prior.server, 'mem_available_bytes') else None
        if available is None:
            available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                 if line.startswith('MemAvailable:'))) * 1024
        if available < CAP + protocol['resources']['memory']['reserve_bytes']:
            raise GateError('fresh MemAvailable below selected cap plus reserve')
        no_other_model()
        port_available()
        stage = 'RUNNING'
        args = SimpleNamespace(run_id=RUN_ID, protocol=root/'protocol.json',
                               suite='c91canary', model='target120b')
        code = server.run(args, protocol, config, [(TASK['id'], TASK)], MODEL)
        raw = strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        samples = [strict_json(line) for line in
                   (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
        maxima = validate_receipt(protocol, config, raw, samples, root,
                                  run_id=RUN_ID, expected_results=1)
        if code != 0:
            raise GateError('runner exit failure')
        if os.stat(MODEL).st_mtime_ns != protocol['c91']['model_stat']['mtime_ns']:
            raise GateError('model changed during canary')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    status = ('PASS_LOAD_AND_SHORT_FORWARD_TESTED_SCOPE' if failure is None else
              'CAPACITY_NOT_ADMITTED' if stage == 'PRELAUNCH' else
              'FAIL_RESOURCES_OR_EVIDENCE')
    decision = {'schema': 'c91-decision-v1', 'status': status,
                'reason': failure, 'measurement_commit': commit,
                'run_id': RUN_ID, 'prelaunch_MemAvailable_bytes': locals().get('available'),
                'model_loaded': bool(raw and raw.get('preflight', {}).get('ready_elapsed_s')),
                'completed_requests': len(raw['results']) if raw else 0,
                'stop_reasons': raw.get('stop_reasons') if raw else None,
                'maxima': maxima, 'claim_limit': protocol['c91']['claim'],
                'historical_failures_unchanged': ['C48', 'C78'],
                'next_action': 'If pass, freeze C80-style 8K OFF/ON numeric boundary under current capacity; otherwise diagnose this new failure.',
                'default_changed': False}
    save_new(root/'decision.json', decision)
    print(json.dumps({'status': status, 'reason': failure, 'maxima': maxima}, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('freeze', 'run'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--measurement-commit')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == 'freeze':
        freeze(root)
    else:
        if not args.measurement_commit:
            parser.error('--measurement-commit required')
        raise SystemExit(run(root, args.measurement_commit))
