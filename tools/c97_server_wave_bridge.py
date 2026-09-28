#!/usr/bin/env python3
"""Frozen two-turn C35/C75 8K server bridge with actual assistant history."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL, MODEL_SHA, digest, validate_receipt
from c17_thermal_recovery import no_other_model
from c85_request_markers import validate as validate_markers
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, relevant_environment, sha256
import c58_resource_canary as c58

REPO = Path(__file__).resolve().parents[1]
BACKENDS = {
    'control': (Path('/tmp/tesy-c35-backend-20260928'), 'build-c35-gcc15',
                'c3759bad92c0e6f71bb936afea9b0a162fb83f76', {}),
    'candidate': (Path('/tmp/tesy-c75-backend-20260928'), 'build-c75-cuda',
                  '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5',
                  {'TESY_CPU_WAVE_SKIP_PARKED': '1'}),
}
ARMS = ('control', 'candidate')
REQUESTS = ('c97-code', 'c97-correction')
CAP = 18 * GIB


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def save_new(path, obj):
    with Path(path).open('x') as out:
        json.dump(obj, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def prior_control_passed(root):
    path = root/'raw'/'control-receipt.json'
    if not path.is_file():
        raise GateError('C97 control receipt absent')
    row = strict_json(path.read_text())
    if row.get('schema') != 'c97-arm-receipt-v1' or \
       row.get('run_id') != 'c97-control01' or \
       row.get('status') != 'PASS_BRIDGE_TESTED_SCOPE' or \
       row.get('completed_requests') != 2 or \
       row.get('reason') is not None:
        raise GateError('C97 control did not pass')
    return row


def input_row(root):
    row = strict_json((root/'session-input.json').read_text())
    if row != {
        'schema': 'c97-session-input-v1', 'base_prefix_words': 1960,
        'first_question': '\nChoose any five-digit code. Reply with the five digits only.',
        'second_question': '\nChange only the last digit of your previous five-digit answer by adding one modulo ten. Reply with the corrected five digits only.',
        'template_date': '2026-09-28', 'max_tokens': 256,
        'temperature': 0, 'seed': 42, 'context_total': 8192,
        'requests': 2, 'inter_request_idle_s': 0,
    }:
        raise GateError('C97 synthetic session input changed')
    return row


def tasks(root):
    row = input_row(root)
    first = 'Context: ' + 'alpha ' * row['base_prefix_words'] + row['first_question']
    return [(key, {'id': key, 'category': 'synthetic-actual-assistant-history',
                   'messages': [{'role': 'user', 'content': first if i == 0 else row['second_question']}],
                   'cache_prompt': True,
                   'chat_template_kwargs': {'tesy_template_date': row['template_date']}})
            for i, key in enumerate(REQUESTS)]


def make(root, arm):
    old, _, model_stat = c58.original()
    snapshot = strict_json((root/'snapshot.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot) != policy or policy['memory']['cap_max_bytes'] < CAP:
        raise GateError('fresh C97 inventory does not admit E18')
    backend, build, expected_sha, env = BACKENDS[arm]
    binary = backend/build/'bin/llama-server'
    if git('-C', backend, 'rev-parse', 'HEAD') != expected_sha or \
       git('-C', backend, 'status', '--porcelain') or not binary.is_file():
        raise GateError('C97 backend changed')
    libraries = backend_library_hashes(str(binary), backend)
    if not libraries:
        raise GateError('C97 backend libraries absent')
    command = list(old['config']['server_command'])
    command[0] = str(binary)
    if command[command.index('-ngl')+1] != '12' or \
       command[command.index('-c')+1] != '8192' or \
       command[command.index('-ub')+1] != '32':
        raise GateError('C97 effective P12 server profile changed')
    row = input_row(root)
    config = {
        'server_command': command, 'explicit_env': env, 'suite': 'c97bridge',
        'task_ids': list(REQUESTS), 'backend_root': str(backend), 'n_ctx': 8192,
        'request_policy': {'mode': 'synthetic-actual-history-bridge', 'attempts': 1,
                           'max_tokens': row['max_tokens'], 'temperature': 0,
                           'seed': 42, 'per_request_timeout_s': 450},
        'total_timeout_s': 960, 'output_root': str((root/'raw').resolve()),
        'pretokenize': True, 'freeze_token_ids': True,
        'append_previous_assistant_to_next': True, 'allow_cache_prompt': True,
        'enforce_output_reserve': True, 'stream_requests': True,
        'inter_request_idle_s': 0, 'dynamic_cache_min_common': 1900,
        'dynamic_cache_max_lost': 32,
        'prompt_token_ranges': {REQUESTS[0]: [1980, 2150],
                                REQUESTS[1]: [1980, 2500]},
        'record_monotonic_request_markers': True,
    }
    identity = dict(old['protocol']['identity'])
    identity.update(model_sha256=MODEL_SHA, backend_sha=expected_sha,
                    binary_sha256=sha256(binary), library_sha256=libraries,
                    config_sha256=digest(config),
                    workload_sha256=sha256(root/'session-input.json'),
                    input_sha256={'session-input.json': sha256(root/'session-input.json')})
    run_id = f'c97-{arm}01'
    protocol = {
        'schema_version': 'c97-protocol-v1', 'campaign_id': root.name,
        'protocol_id': run_id+'-v1', 'identity': identity,
        'expected_request_ids': list(REQUESTS),
        'limits': {'max_gap_s': 3, 'boundary_s': 2},
        'resources': freeze_protocol_resource_limits(policy, cgroup_memory_max_bytes=CAP),
        'trace': {'request_marker_schema': 'c85-request-monotonic-v1'},
        'c97': {'arm': arm, 'order': ARMS.index(arm)+1,
                'model_stat': model_stat,
                'backend_tree': git('-C', backend, 'rev-parse', 'HEAD^{tree}'),
                'runner_sha256': sha256(__file__),
                'claim': 'one contemporary two-turn actual-history server bridge; descriptive latency only; not a performance promotion'},
    }
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C97 new root/raw/protocols required')
    for arm in ARMS:
        protocol, config = make(root, arm)
        save_new(root/'protocols'/f'c97-{arm}01.json', protocol)
        save_new(root/f'{arm}-config.json', config)
    save_new(root/'preflight.json', {
        'schema': 'c97-freeze-v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'snapshot_sha256': sha256(root/'snapshot.json'),
        'resource_policy_sha256': sha256(root/'resource-policy.json'),
        'input_sha256': sha256(root/'session-input.json'),
        'protocol_sha256': {arm: sha256(root/'protocols'/f'c97-{arm}01.json') for arm in ARMS},
        'config_sha256': {arm: sha256(root/f'{arm}-config.json') for arm in ARMS},
        'status': 'FROZEN_NOT_MEASURED',
    })


def run(root, arm, commit):
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C97 measurement commit/worktree/environment changed')
    protocol, config = make(root, arm)
    run_id = f'c97-{arm}01'
    path = root/'protocols'/f'{run_id}.json'
    pre = strict_json((root/'preflight.json').read_text())
    if strict_json(path.read_text()) != protocol or \
       strict_json((root/f'{arm}-config.json').read_text()) != config or \
       sha256(path) != pre['protocol_sha256'][arm] or \
       sha256(root/f'{arm}-config.json') != pre['config_sha256'][arm] or \
       sha256(root/'snapshot.json') != pre['snapshot_sha256'] or \
       sha256(root/'resource-policy.json') != pre['resource_policy_sha256'] or \
       sha256(root/'session-input.json') != pre['input_sha256']:
        raise GateError('C97 frozen protocol or inputs changed')
    if arm == 'candidate':
        prior_control_passed(root)
    no_other_model()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 18367))
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    if available < CAP + protocol['resources']['memory']['reserve_bytes']:
        raise GateError('C97 E18 host reserve no longer admitted')
    failure = None
    raw = None
    maxima = None
    try:
        args = SimpleNamespace(run_id=run_id, protocol=path, suite='c97bridge', model='target120b')
        code = server.run(args, protocol, config, tasks(root), MODEL)
        raw = strict_json((root/'raw'/f'{run_id}.json').read_text())
        samples = [strict_json(line) for line in
                   (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
        maxima = validate_receipt(protocol, config, raw, samples, root,
                                  run_id=run_id, protocol_filename=f'protocols/{run_id}.json',
                                  expected_results=2)
        if code != 0:
            raise GateError('C97 server runner exit failure')
        ids = strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
        if list(ids) != list(REQUESTS):
            raise GateError('C97 official token IDs incomplete')
        markers = validate_markers(root/'raw'/f'{run_id}.request-markers.jsonl',
                                   run_id, REQUESTS, raw['results'])
        if markers['status'] != 'PASS':
            raise GateError('C97 request marker receipt incomplete')
        for item in raw['results']:
            stream = item.get('stream_metrics')
            usage = item.get('usage')
            if item.get('finish_reason') != 'stop' or \
               type(stream) is not dict or stream.get('done_observed') is not True or \
               type(stream.get('first_final_content_chunk_s')) not in (int, float) or \
               not math.isfinite(stream['first_final_content_chunk_s']) or \
               type(usage) is not dict or usage.get('prompt_tokens') != len(ids[item['id']]) or \
               not 0 < usage.get('completion_tokens', 0) < input_row(root)['max_tokens'] or \
               not item['message'].get('content'):
                raise GateError('C97 response/final-content/completion incomplete')
        if os.stat(MODEL).st_mtime_ns != protocol['c97']['model_stat']['mtime_ns']:
            raise GateError('C97 model stat changed during run')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    receipt = {
        'schema': 'c97-arm-receipt-v1', 'arm': arm, 'run_id': run_id,
        'measurement_commit': commit,
        'status': 'PASS_BRIDGE_TESTED_SCOPE' if failure is None else 'FAIL_RESOURCES_OR_EVIDENCE',
        'reason': failure, 'completed_requests': len(raw['results']) if raw else 0,
        'stop_reasons': raw.get('stop_reasons') if raw else None,
        'maxima': maxima, 'raw_sha256': sha256(root/'raw'/f'{run_id}.json') if raw else None,
        'default_changed': False,
    }
    save_new(root/'raw'/f'{arm}-receipt.json', receipt)
    print(json.dumps(receipt, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('freeze', 'run'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--arm', choices=ARMS)
    parser.add_argument('--measurement-commit')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == 'freeze':
        freeze(root)
    else:
        if not args.arm or not args.measurement_commit:
            parser.error('run requires arm and measurement commit')
        raise SystemExit(run(root, args.arm, args.measurement_commit))
