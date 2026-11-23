#!/usr/bin/env python3
"""C112 nominal 128-word incremental server fixture using C97's mature bridge."""

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
REQUESTS = ('c112-code', 'c112-repeat')
CAP = 18 * GIB


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def save_new(path, obj):
    with Path(path).open('x') as out:
        json.dump(obj, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def input_row(root):
    row = strict_json((root/'session-input.json').read_text())
    if row != {
        'schema': 'c112-session-input-v1', 'base_prefix_words': 1960,
        'increment_beta_words': 127,
        'first_question': '\nChoose any five-digit code. Reply with the five digits only.',
        'second_question': '\nRepeat the exact text of your immediately previous answer, with no additions.',
        'template_date': '2026-09-29', 'max_tokens': 256,
        'temperature': 0, 'seed': 42, 'context_total': 8192,
        'requests': 2, 'inter_request_idle_s': 0,
    }:
        raise GateError('C112 synthetic session input changed')
    return row


def tasks(root):
    row = input_row(root)
    first = 'Context: ' + 'alpha ' * row['base_prefix_words'] + row['first_question']
    second = ' beta' * row['increment_beta_words'] + row['second_question']
    return [(key, {'id': key, 'category': 'synthetic-actual-assistant-history',
                   'messages': [{'role': 'user', 'content': first if i == 0 else second}],
                   'cache_prompt': True,
                   'chat_template_kwargs': {'tesy_template_date': row['template_date']}})
            for i, key in enumerate(REQUESTS)]


def make(root, arm):
    old, _, model_stat = c58.original()
    snapshot = strict_json((root/'snapshot.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot) != policy or policy['memory']['cap_max_bytes'] < CAP:
        raise GateError('fresh C112 inventory does not admit E18')
    backend, build, expected_sha, env = BACKENDS[arm]
    binary = backend/build/'bin/llama-server'
    if git('-C', backend, 'rev-parse', 'HEAD') != expected_sha or \
       git('-C', backend, 'status', '--porcelain') or not binary.is_file():
        raise GateError('C112 backend changed')
    libraries = backend_library_hashes(str(binary), backend)
    if not libraries:
        raise GateError('C112 backend libraries absent')
    command = list(old['config']['server_command'])
    command[0] = str(binary)
    if command[command.index('-ngl')+1] != '12' or \
       command[command.index('-c')+1] != '8192' or \
       command[command.index('-ub')+1] != '32':
        raise GateError('C112 effective P12 server profile changed')
    row = input_row(root)
    config = {
        'server_command': command, 'explicit_env': env, 'suite': 'c112nominal',
        'task_ids': list(REQUESTS), 'backend_root': str(backend), 'n_ctx': 8192,
        'request_policy': {'mode': 'nominal128-actual-history-bridge', 'attempts': 1,
                           'max_tokens': row['max_tokens'], 'temperature': 0,
                           'seed': 42, 'per_request_timeout_s': 450},
        'total_timeout_s': 600, 'output_root': str((root/'raw').resolve()),
        'pretokenize': True, 'freeze_token_ids': True,
        'append_previous_assistant_to_next': True, 'allow_cache_prompt': True,
        'enforce_output_reserve': True, 'stream_requests': True,
        'inter_request_idle_s': 0, 'dynamic_cache_min_common': 1900,
        'dynamic_cache_max_lost': 32,
        'prompt_token_ranges': {REQUESTS[0]: [1980, 2150],
                                REQUESTS[1]: [2100, 2500]},
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

