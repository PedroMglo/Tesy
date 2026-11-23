#!/usr/bin/env python3
"""One frozen minimum API forward after C9 init-only admission."""

import argparse
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
import c8_observer_runner as budget_runner
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c7_timing_runner import cool_start
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import (MODEL, RUN_ID as INIT_RUN_ID, configuration,
                                 digest, environment, git, validate_receipt)
from run_bounded import sha256

RUN_ID = 'c9-g2-forward'
REQUEST_ID = 'c9-minimum-forward'


def frozen(root):
    protocol, config = configuration(root)
    forward = strict_json((root / 'forward-input.json').read_text())
    if forward != {'schema': 'c9-minimum-forward-input-v1', 'id': REQUEST_ID,
                   'category': 'diagnostic',
                   'prompt': 'Return the integer value of 7 + 5.',
                   'max_tokens': 4, 'temperature': 0, 'seed': 42}:
        raise GateError('minimum-forward input changed')
    if strict_json((root / 'admission.json').read_text())['status'] != \
       'CAPACITY_ADMITTED_INIT_ONLY':
        raise GateError('init-only admission prerequisite missing')
    config['suite'] = 'c9forward'
    config['task_ids'] = [REQUEST_ID]
    config['request_policy'] = {'mode': 'minimum-forward', 'attempts': 1,
                                'max_tokens': 4, 'temperature': 0, 'seed': 42,
                                'prompt_cache': True, 'per_request_timeout_s': 120}
    config['total_timeout_s'] = 180
    protocol['protocol_id'] = 'c9-8k-server-minimum-forward-v1'
    protocol['expected_request_ids'] = [REQUEST_ID]
    protocol['identity']['config_sha256'] = digest(config)
    protocol['identity']['workload_sha256'] = sha256(root / 'forward-input.json')
    protocol['identity']['input_sha256'] = {
        'forward-input.json': sha256(root / 'forward-input.json'),
        'usage-contract.json': sha256(root / 'usage-contract.json')}
    protocol['c9']['mode'] = 'minimum-forward'
    protocol['c9']['claim'] = 'one short 8K-context API request; no 8K-length workload claim'
    protocol['c9']['forward_runner_sha256'] = sha256(__file__)
    protocol['c9']['budget_runner_sha256'] = sha256(budget_runner.__file__)
    return protocol, config, forward


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--run', action='store_true')
    p.add_argument('--measurement-commit')
    args = p.parse_args()
    root = args.root.resolve()
    if not (root / 'raw' / f'{INIT_RUN_ID}.json').is_file():
        p.error('C9 init raw missing')
    protocol, config, forward = frozen(root)
    destination = root / 'forward-protocol03.json'
    if args.freeze:
        with destination.open('x') as f:
            json.dump(protocol, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
        print('frozen', destination)
        return 0
    if not args.measurement_commit or git('rev-parse', 'HEAD') != args.measurement_commit or \
       git('status', '--porcelain') or strict_json(destination.read_text()) != protocol:
        p.error('measurement commit/worktree/forward protocol changed')
    if model_stat() != protocol['c9']['model_stat'] or \
       program_physical_consumed() + 210 > 16 * 3600:
        p.error('model identity/physical budget changed')
    environment()
    cool = cool_start(root, 180)
    task = {'id': REQUEST_ID, 'category': forward['category'], 'prompt': forward['prompt']}
    args_c2 = SimpleNamespace(model='target120b', suite='c9forward', run_id=RUN_ID,
                              protocol=destination)
    returncode = server.run(args_c2, protocol, config, [(REQUEST_ID, task)], MODEL)
    raw_path = root / 'raw' / f'{RUN_ID}.json'
    raw = strict_json(raw_path.read_text())
    samples = [strict_json(line) for line in
               (root / 'raw' / f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    status = 'MINIMUM_FORWARD_ADMITTED' if returncode == 0 else 'FAIL_RESOURCES_OR_EVIDENCE'
    reason = None
    maxima = None
    numeric = None
    try:
        maxima = validate_receipt(protocol, config, raw, samples, root,
                                  run_id=RUN_ID, protocol_filename='forward-protocol03.json',
                                  expected_results=1)
        normalized = strict_json((root / 'raw' / f'{RUN_ID}.normalized.json').read_text())
        numeric = validate_c2(normalized, {name: protocol[name] for name in PROTOCOL})
        row = raw['results'][0]
        if row['id'] != REQUEST_ID or row['usage']['completion_tokens'] != 4 or \
           row['usage']['prompt_tokens'] + 4 > 8192 or \
           row['timings']['cache_n'] != 0 or \
           row['finish_reason'] != 'length' or model_stat() != protocol['c9']['model_stat']:
            raise GateError('minimum-forward input, output reserve, cache or model identity invalid')
    except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
        status = 'FAIL_RESOURCES_OR_EVIDENCE'
        reason = f'{type(exc).__name__}: {exc}'
    receipt = {'schema': 'c9-minimum-forward-v1', 'status': status,
               'run_id': RUN_ID, 'measurement_commit': args.measurement_commit,
               'reason': reason, 'cool_start': cool, 'server_returncode': returncode,
               'elapsed_s': raw['elapsed_s'], 'raw_sha256': sha256(raw_path),
               'protocol_sha256': sha256(destination), 'sample_count': len(samples),
               'maxima': maxima, 'server_gate': numeric,
               'usage': raw['results'][0]['usage'] if raw['results'] else None,
               'timings': raw['results'][0]['timings'] if raw['results'] else None,
               'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'claim_limit': 'one short API forward with 8K context; 512/2048/4096 and boundary 7936 NOT_RUN'}
    with (root / 'forward-admission.json').open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
    print(json.dumps({'status': status, 'reason': reason, 'maxima': maxima}, allow_nan=False))
    return 0 if status == 'MINIMUM_FORWARD_ADMITTED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
