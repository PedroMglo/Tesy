#!/usr/bin/env python3
"""Bounded P16 slots24 8K server resource diagnostics, no timing promotion."""

import argparse
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
import c8_observer_runner as budget_reader
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c7_timing_runner import cool_start
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, configuration, digest, environment, git, validate_receipt
from run_bounded import sha256

MODES = {'init': ('c12-g1-init',120,'CAPACITY_ADMITTED_INIT_ONLY'),
         'forward': ('c12-g2-forward',180,'MINIMUM_FORWARD_ADMITTED_NEW_PROFILE'),
         'short513': ('c12-g3-short513',300,'SHORT513_RESOURCE_PASS_NUMERIC_NOT_PROMOTED')}


def frozen(root, mode):
    protocol, config = configuration(root)
    spec = strict_json((root / 'input.json').read_text())
    command = config['server_command']
    if command[command.index('-ngl')+1] != '8' or command[command.index('-ub')+1] != '32' or command[command.index('--moe-stream-cache')+1] != '32s':
        raise GateError('expected P8/ub32/slots32 server base changed')
    command[command.index('-ngl')+1] = '16'
    command[command.index('--moe-stream-cache')+1] = '24s'
    run_id, timeout, _ = MODES[mode]
    task = None
    config.update({'suite': f'c12{mode}', 'total_timeout_s': timeout,
                   'request_policy': {'mode': mode, 'attempts': 1,
                                      'max_tokens': 4, 'temperature': 0,
                                      'seed': 42, 'per_request_timeout_s': timeout-20,
                                      'prompt_cache': True}})
    if mode != 'init':
        source = spec['minimum_forward'] if mode == 'forward' else spec['short513']
        task = {'id': source['id'], 'category': 'synthetic-resource',
                'prompt': source['prompt'], 'cache_prompt': True}
        config.update({'task_ids': [source['id']], 'n_ctx': 8192,
                       'pretokenize': True, 'freeze_token_ids': True,
                       'enforce_output_reserve': True,
                       'prompt_token_ranges': {source['id']: source['expected_prompt_tokens']}})
    protocol['campaign_id'] = 'tesy-c12-20260927'
    protocol['protocol_id'] = f'c12-p16s24-8k-{mode}-v1'
    protocol['expected_request_ids'] = config['task_ids']
    protocol['identity']['config_sha256'] = digest(config)
    protocol['identity']['workload_sha256'] = sha256(root / 'input.json')
    protocol['identity']['input_sha256'] = {
        'input.json': sha256(root / 'input.json'),
        'usage-contract.json': sha256(root / 'usage-contract.json')}
    prior = protocol.pop('c9')
    protocol['c12'] = {'mode': mode, 'n_gpu_layers': 16, 'n_ubatch': 32, 'slots': 24, 'new_numeric_profile': True,
                       'model_stat': prior['model_stat'],
                       'backend_tree': prior['backend_tree'],
                       'server_monitor_sha256': sha256(server.__file__),
                       'budget_reader_sha256': sha256(budget_reader.__file__),
                       'runner_sha256': sha256(__file__),
                       'measurement_scope': 'resource/capacity diagnostic only; same-profile numeric reference NOT_RUN'}
    tasks = [] if task is None else [(task['id'], task)]
    return protocol, config, tasks


def run_mode(root, mode, commit):
    protocol, config, tasks = frozen(root, mode)
    run_id, timeout, pass_status = MODES[mode]
    protocol_path = root / f'{mode}-protocol.json'
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or \
       strict_json(protocol_path.read_text()) != protocol or \
       model_stat() != protocol['c12']['model_stat']:
        raise GateError('p16s24 measurement commit/profile changed')
    if program_physical_consumed()+timeout+30 > 16*3600:
        raise GateError('physical budget cannot cover C12 unit')
    if mode == 'forward' and strict_json((root/'init-admission.json').read_text())['status'] != \
       MODES['init'][2]:
        raise GateError('C12 init prerequisite absent')
    if mode == 'short513' and strict_json((root/'forward-admission.json').read_text())['status'] != \
       MODES['forward'][2]:
        raise GateError('C12 forward prerequisite absent')
    environment()
    cool = cool_start(root, timeout)
    if cool['cpu_c'] > 55:
        raise GateError('CPU start temperature exceeds the frozen 55 C precondition')
    args_c2 = SimpleNamespace(model='target120b', suite=f'c12{mode}', run_id=run_id,
                              protocol=protocol_path)
    try:
        rc = server.run(args_c2, protocol, config, tasks, MODEL)
        launch_error = None
    except (GateError, OSError, ValueError, RuntimeError) as exc:
        rc = 1
        launch_error = f'{type(exc).__name__}: {exc}'
    raw_path = root / 'raw' / f'{run_id}.json'
    raw = strict_json(raw_path.read_text()) if raw_path.exists() else None
    receipt = {'schema': 'c12-p16s24-server-unit-v1', 'mode': mode,
               'run_id': run_id, 'measurement_commit': commit,
               'status': 'FAIL_RESOURCES_OR_EVIDENCE', 'reason': launch_error,
               'cool_start': cool, 'server_returncode': rc,
               'raw_sha256': sha256(raw_path) if raw else None,
               'protocol_sha256': sha256(protocol_path),
               'elapsed_s': raw['elapsed_s'] if raw else None,
               'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'numeric_claim': 'NOT_RUN: P16 slots24 server reference/observer'}
    if raw is not None:
        try:
            if rc != 0:
                raise GateError('server monitor/normalization failed: ' + str(raw['stop_reasons']))
            samples = [strict_json(line) for line in
                       (root / 'raw' / f'{run_id}.samples.jsonl').read_text().splitlines()]
            maxima = validate_receipt(protocol, config, raw, samples, root,
                                      run_id=run_id, protocol_filename=f'{mode}-protocol.json',
                                      expected_results=len(tasks))
            receipt.update(maxima=maxima, sample_count=len(samples))
            if mode != 'init':
                normalized = strict_json((root / 'raw' / f'{run_id}.normalized.json').read_text())
                receipt['server_gate'] = validate_c2(normalized,
                                                    {name:protocol[name] for name in PROTOCOL})
                ids = strict_json((root / 'raw' / f'{run_id}.tokenization.json').read_text())
                request_id = tasks[0][0]
                source = strict_json((root/'input.json').read_text())[
                    'minimum_forward' if mode == 'forward' else 'short513']
                if set(ids) != {request_id} or \
                   not source['expected_prompt_tokens'][0] <= len(ids[request_id]) <= \
                       source['expected_prompt_tokens'][1] or \
                   raw['preflight']['prompt_tokenization'][request_id]['token_ids_sha256'] != \
                       digest(ids[request_id]):
                    raise GateError('official tokenizer IDs/count/hash differ from freeze')
                row = raw['results'][0]
                if row['usage']['prompt_tokens'] != len(ids[request_id]) or \
                   row['timings']['cache_n'] != 0 or \
                   not 0 < row['usage']['completion_tokens'] <= 4 or \
                   len(ids[request_id])+4 > 8192:
                    raise GateError('request usage/cache/output reserve invalid')
                receipt.update(usage=row['usage'],timings=row['timings'],
                               token_ids_sha256=digest(ids[request_id]))
            if model_stat() != protocol['c12']['model_stat']:
                raise GateError('model file stat changed')
            receipt['status'] = pass_status
            receipt['reason'] = None
        except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
            receipt['reason'] = f'{type(exc).__name__}: {exc}'
    with (root / f'{mode}-admission.json').open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
    print(json.dumps({'mode':mode,'status':receipt['status'],'reason':receipt['reason'],
                      'maxima':receipt.get('maxima')},allow_nan=False),flush=True)
    return 0 if receipt['status'] == pass_status else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    p.add_argument('--freeze',action='store_true')
    p.add_argument('--run',choices=MODES)
    p.add_argument('--measurement-commit')
    args = p.parse_args()
    if args.freeze == bool(args.run):
        p.error('choose exactly one of --freeze or --run')
    root = args.root.resolve()
    if args.freeze:
        for mode in MODES:
            protocol,_,_ = frozen(root,mode)
            with (root/f'{mode}-protocol.json').open('x') as f:
                json.dump(protocol,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
        print('frozen C12 init, minimum forward, short513 protocols')
        return 0
    if not args.measurement_commit:
        p.error('measurement commit required')
    return run_mode(root,args.run,args.measurement_commit)


if __name__ == '__main__':
    raise SystemExit(main())
