#!/usr/bin/env python3
"""New candidate-only bridge using the hash-verified C97 contemporary control."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL, validate_receipt
from c17_thermal_recovery import no_other_model
from c85_request_markers import validate as validate_markers
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import relevant_environment, sha256
import c97_server_wave_bridge as prior

CONTROL = prior.REPO/'results/c97-session-wave-server-20260928T2133Z'
RUN_ID = 'c98-candidate01'
CAP = 18 * GIB


def save_new(path, obj):
    with Path(path).open('x') as out:
        json.dump(obj, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def control_evidence():
    receipt = strict_json((CONTROL/'control-receipt.json').read_text())
    manifest = strict_json((CONTROL/'manifest.json').read_text())
    decision = strict_json((CONTROL/'decision.json').read_text())
    raw = CONTROL/'raw/c97-control01.json'
    if receipt.get('status') != 'PASS_BRIDGE_TESTED_SCOPE' or \
       decision.get('control') != 'PASS_BRIDGE_TESTED_SCOPE' or \
       decision.get('candidate') != 'NOT_RUN_MODEL' or \
       receipt.get('raw_sha256') != sha256(raw) or \
       manifest['raw']['c97-control01.json']['sha256'] != sha256(raw) or \
       manifest['raw']['control-receipt.json']['sha256'] != sha256(CONTROL/'raw/control-receipt.json'):
        raise GateError('C97 contemporary control evidence changed/incomplete')
    return {'receipt_sha256': sha256(CONTROL/'control-receipt.json'),
            'manifest_sha256': sha256(CONTROL/'manifest.json'),
            'decision_sha256': sha256(CONTROL/'decision.json'),
            'raw_sha256': sha256(raw)}


def make(root):
    control = control_evidence()
    protocol, config = prior.make(root, 'candidate')
    config['suite'] = 'c98bridge'
    protocol['schema_version'] = 'c98-protocol-v1'
    protocol['protocol_id'] = RUN_ID+'-v1'
    protocol['identity']['config_sha256'] = server.digest(config)
    old = protocol.pop('c97')
    protocol['c98'] = {
        'arm': 'candidate', 'comparison_control': 'C97 c97-control01',
        'control_evidence_sha256': control,
        'model_stat': old['model_stat'], 'backend_tree': old['backend_tree'],
        'base_harness_sha256': sha256(prior.__file__),
        'runner_sha256': sha256(__file__),
        'claim': 'candidate-only two-turn server bridge against hash-frozen C97 control; no performance promotion',
    }
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C98 new root/raw/protocols required')
    protocol, config = make(root)
    save_new(root/'protocols'/f'{RUN_ID}.json', protocol)
    save_new(root/'config.json', config)
    save_new(root/'preflight.json', {
        'schema': 'c98-freeze-v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'snapshot_sha256': sha256(root/'snapshot.json'),
        'resource_policy_sha256': sha256(root/'resource-policy.json'),
        'input_sha256': sha256(root/'session-input.json'),
        'control_evidence_sha256': control_evidence(),
        'protocol_sha256': sha256(root/'protocols'/f'{RUN_ID}.json'),
        'config_sha256': sha256(root/'config.json'),
        'status': 'FROZEN_NOT_MEASURED',
    })


def run(root, commit):
    if prior.git('rev-parse', 'HEAD') != commit or prior.git('status', '--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C98 measurement commit/worktree/environment changed')
    protocol, config = make(root)
    path = root/'protocols'/f'{RUN_ID}.json'
    pre = strict_json((root/'preflight.json').read_text())
    if strict_json(path.read_text()) != protocol or \
       strict_json((root/'config.json').read_text()) != config or \
       sha256(path) != pre['protocol_sha256'] or \
       sha256(root/'config.json') != pre['config_sha256'] or \
       sha256(root/'snapshot.json') != pre['snapshot_sha256'] or \
       sha256(root/'resource-policy.json') != pre['resource_policy_sha256'] or \
       sha256(root/'session-input.json') != pre['input_sha256'] or \
       control_evidence() != pre['control_evidence_sha256']:
        raise GateError('C98 frozen input/protocol/control differs')
    no_other_model()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    if available < CAP + protocol['resources']['memory']['reserve_bytes']:
        raise GateError('C98 E18 host reserve no longer admitted')
    failure = None
    raw = None
    maxima = None
    try:
        args = SimpleNamespace(run_id=RUN_ID, protocol=path, suite='c98bridge', model='target120b')
        code = server.run(args, protocol, config, prior.tasks(root), MODEL)
        raw = strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        samples = [strict_json(line) for line in
                   (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
        maxima = validate_receipt(protocol, config, raw, samples, root,
                                  run_id=RUN_ID, protocol_filename=f'protocols/{RUN_ID}.json',
                                  expected_results=2)
        if code != 0:
            raise GateError('C98 server runner exit failure')
        ids = strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())
        if list(ids) != list(prior.REQUESTS):
            raise GateError('C98 official token IDs incomplete')
        marker = validate_markers(root/'raw'/f'{RUN_ID}.request-markers.jsonl',
                                  RUN_ID, prior.REQUESTS, raw['results'])
        if marker['status'] != 'PASS':
            raise GateError('C98 monotonic markers incomplete')
        for item in raw['results']:
            stream, usage = item.get('stream_metrics'), item.get('usage')
            if item.get('finish_reason') != 'stop' or \
               type(stream) is not dict or stream.get('done_observed') is not True or \
               type(stream.get('first_final_content_chunk_s')) not in (int, float) or \
               not math.isfinite(stream['first_final_content_chunk_s']) or \
               type(usage) is not dict or usage.get('prompt_tokens') != len(ids[item['id']]) or \
               not 0 < usage.get('completion_tokens', 0) < prior.input_row(root)['max_tokens'] or \
               not item['message'].get('content'):
                raise GateError('C98 response/final-content/completion incomplete')
        if os.stat(MODEL).st_mtime_ns != protocol['c98']['model_stat']['mtime_ns']:
            raise GateError('C98 model stat changed during run')
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    receipt = {
        'schema': 'c98-arm-receipt-v1', 'run_id': RUN_ID,
        'measurement_commit': commit,
        'status': 'PASS_BRIDGE_TESTED_SCOPE' if failure is None else 'FAIL_RESOURCES_OR_EVIDENCE',
        'reason': failure, 'completed_requests': len(raw['results']) if raw else 0,
        'stop_reasons': raw.get('stop_reasons') if raw else None,
        'maxima': maxima, 'raw_sha256': sha256(root/'raw'/f'{RUN_ID}.json') if raw else None,
        'default_changed': False,
    }
    save_new(root/'raw'/'candidate-receipt.json', receipt)
    print(json.dumps(receipt, allow_nan=False))
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
