#!/usr/bin/env python3
"""Prospective CPU100 retest of the C13 exact-prefix ON mechanism."""

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, configuration, digest, git, validate_receipt
from run_bounded import sha256

ARMS = ('on',)
REQUESTS = ('c13-prefix512', 'c13-increment128')
RUN_ID = 'c19-g1-prefix-on'
C13_ROOT = Path('results/c13-20260927T1550Z')
C17_ROOT = Path('results/c17-thermal-recovery-20260927T1656Z')
C18_ROOT = Path('results/c18-cpu100-retest-20260927T1756Z')


def workload(root):
    row = strict_json((root / 'prefix-input.json').read_text())
    if row['schema'] != 'c13-prefix-diagnostic-input-v1' or \
       row['prefix_text'] != 'alpha '*445 or row['increment_text'] != ' beta'*128 or \
       row['first_request_output_cap'] != 4 or row['second_request_output_cap'] != 4:
        raise GateError('frozen synthetic prefix input changed')
    return row


def frozen(root, arm):
    protocol, config = configuration(root)
    command = config['server_command']
    if command[command.index('-ngl')+1] != '8' or command[command.index('-ub')+1] != '32':
        raise GateError('expected P8/ub32 server base changed')
    command[command.index('-ngl')+1] = '12'
    row = workload(root)
    config.update({'suite': 'c13prefix', 'arm': arm,
                   'task_ids': list(REQUESTS), 'n_ctx': 8192,
                   'pretokenize': True, 'freeze_token_ids': True,
                   'allow_cache_prompt': True, 'enforce_output_reserve': True,
                   'prompt_token_ranges': {
                       REQUESTS[0]: [row['token_count_policy']['first_min'],
                                     row['token_count_policy']['first_max']],
                       REQUESTS[1]: [row['token_count_policy']['second_min'],
                                     row['token_count_policy']['second_max']]},
                   'request_policy': {'mode': 'synthetic-prefix-mechanism',
                                      'attempts': 1, 'max_tokens': 4,
                                      'temperature': 0, 'seed': 42,
                                      'per_request_timeout_s': 260,
                                      'cache_second': arm == 'on'},
                   'total_timeout_s': 300})
    config['suite'] = 'c19prefix'
    prior = strict_json((C13_ROOT / 'raw/c13-g1-prefix-on.preflight.json').read_text())['config']
    common = {'server_command', 'explicit_env', 'arm', 'task_ids', 'n_ctx',
              'pretokenize', 'freeze_token_ids', 'allow_cache_prompt',
              'enforce_output_reserve', 'prompt_token_ranges', 'request_policy',
              'total_timeout_s'}
    if {key: config[key] for key in common} != {key: prior[key] for key in common} or \
            sha256(root / 'prefix-input.json') != sha256(C13_ROOT / 'prefix-input.json') or \
            sha256(root / 'usage-contract.json') != sha256(C13_ROOT / 'usage-contract.json'):
        raise GateError('C19 runtime/input differs from interrupted C13 arm')
    prior_protocol = strict_json((C13_ROOT/'prefix-protocol-on.json').read_text())
    if any(protocol['identity'][key] != prior_protocol['identity'][key] for key in
           ('model_sha256','backend_sha','binary_sha256','library_sha256')):
        raise GateError('C19 model/backend/binary/library differs from interrupted C13 arm')
    protocol['campaign_id'] = 'tesy-c19-cpu100-prefix-retest-20260927'
    protocol['protocol_id'] = f'c19-p12-8k-prefix-{arm}-v1'
    protocol['expected_request_ids'] = list(REQUESTS)
    protocol['identity']['config_sha256'] = digest(config)
    protocol['identity']['workload_sha256'] = sha256(root / 'prefix-input.json')
    protocol['identity']['input_sha256'] = {
        'prefix-input.json': sha256(root / 'prefix-input.json'),
        'usage-contract.json': sha256(root / 'usage-contract.json')}
    protocol['limits']['cpu_max_c'] = 100
    protocol['c19'] = protocol.pop('c9')
    protocol['c19'].update(mode='synthetic-prefix-mechanism', n_gpu_layers=12,
                           arm=arm, prefix_runner_sha256=sha256(__file__),
                           claim='one ON arm: direct cache mechanism and resource diagnostic, no timing/session/quality confirmation')
    protocol['c18'] = {'thermal_monitor':'CPU95 warning, CPU100/explicit cooling/clock collapse stop',
                       'monitor_sha256':sha256(server.__file__)}
    messages1 = [{'role': 'user', 'content': row['prefix_text']}]
    messages2 = [{'role': 'user', 'content': row['prefix_text'] + row['increment_text']}]
    tasks = [(REQUESTS[0], {'id': REQUESTS[0], 'category': 'synthetic-prefix',
                            'messages': messages1, 'cache_prompt': True}),
             (REQUESTS[1], {'id': REQUESTS[1], 'category': 'synthetic-prefix',
                            'messages': messages2, 'cache_prompt': arm == 'on'})]
    return protocol, config, tasks, row


def validate_arm(root, arm, protocol, config, raw):
    run_id = RUN_ID
    samples = [strict_json(line) for line in
               (root / 'raw' / f'{run_id}.samples.jsonl').read_text().splitlines()]
    maxima = validate_receipt(protocol, config, raw, samples, root,
                              run_id=run_id, protocol_filename=f'prefix-protocol-{arm}.json',
                              expected_results=2)
    cpu = summarize_samples(samples, require_safe=True)
    normalized = strict_json((root / 'raw' / f'{run_id}.normalized.json').read_text())
    server_gate = validate_c2(normalized, {name: protocol[name] for name in PROTOCOL})
    ids = strict_json((root / 'raw' / f'{run_id}.tokenization.json').read_text())
    if set(ids) != set(REQUESTS) or any(type(x) is not int for values in ids.values() for x in values):
        raise GateError('frozen tokenizer ID set invalid')
    pretoken = raw['preflight']['prompt_tokenization']
    for request_id in REQUESTS:
        if pretoken[request_id]['count'] != len(ids[request_id]) or \
           pretoken[request_id]['token_ids_sha256'] != digest(ids[request_id]):
            raise GateError('tokenizer raw/hash mismatch')
    common = 0
    for a, b in zip(ids[REQUESTS[0]], ids[REQUESTS[1]]):
        if a != b:
            break
        common += 1
    if common < workload(root)['common_prefix_min_ids']:
        raise GateError('tokenized common prefix below frozen minimum')
    results = raw['results']
    first, second = (x['timings'] for x in results)
    if first['cache_n'] != 0 or any(x['usage']['prompt_tokens'] != len(ids[x['id']]) for x in results):
        raise GateError('first request cache or official token counts invalid')
    if any(x['usage']['completion_tokens'] <= 0 or x['usage']['completion_tokens'] > 4 for x in results):
        raise GateError('completion count outside frozen cap')
    status = 'PASS_MECHANISM' if (second['cache_n'] >= workload(root)['cache_on_expected_reuse_min_ids']
                                  if arm == 'on' else second['cache_n'] == 0) else \
             'PREFIX_REUSE_NOT_OBSERVED'
    if second['cache_n'] > common:
        raise GateError('cache reuse exceeds actual common prefix')
    return status, maxima, cpu, server_gate, common, ids


def run_arm(root, arm, commit):
    run_id = RUN_ID
    protocol_path = root / f'prefix-protocol-{arm}.json'
    protocol, config, tasks, _ = frozen(root, arm)
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or \
       strict_json(protocol_path.read_text()) != protocol or \
       model_stat() != protocol['c19']['model_stat']:
        raise GateError('prefix arm differs from frozen commit/identity')
    previous_idle_s = 394.4515725659985
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C17_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C18_ROOT.glob('*-idle.json'))
    if program_physical_consumed() + previous_idle_s + 900 + 330 > 16*3600:
        raise GateError('physical time budget cannot cover C13 prefix arm')
    if strict_json((C18_ROOT/'decision.json').read_text())['status'] != 'THERMAL_RETTEST_PASS':
        raise GateError('C18 four cold513 arms did not qualify')
    preflight = strict_json((root/'preflight.json').read_text())
    if preflight['guard_status'] != 'READY_FOR_IDLE_ADMISSION' or \
       preflight['power_source'] != 'AC' or \
       Path('/sys/class/power_supply/AC0/online').read_text().strip() != '1' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip() != preflight['power_profile']:
        raise GateError('C19 host/power preflight changed')
    scope = check_scope()
    no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('processor cooling active before C19 idle')
    idle = thermal_idle(root, run_id)
    with (root / f'{run_id}-idle.json').open('x') as out:
        json.dump(idle,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    if idle['status'] != 'PASS':
        receipt = {'schema':'c19-prefix-receipt-v1','run_id':run_id,
                   'measurement_commit':commit,'status':'THERMAL_PREFLIGHT_BLOCKED',
                   'idle':idle,'model_runs':0,'default_changed':False}
        with (root/f'{run_id}-receipt.json').open('x') as out:
            json.dump(receipt,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        return 2
    if check_scope() != scope or cpu_capture()['processor_cooling_max_state'] or \
       Path('/sys/class/power_supply/AC0/online').read_text().strip() != '1' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip() != preflight['power_profile']:
        raise GateError('scope/CPU mitigation/power profile changed after C19 idle')
    no_other_model()
    args_c2 = SimpleNamespace(model='target120b', suite='c19prefix', run_id=run_id,
                              protocol=protocol_path)
    returncode = server.run(args_c2, protocol, config, tasks, MODEL)
    raw_path = root / 'raw' / f'{run_id}.json'
    raw = strict_json(raw_path.read_text())
    status = 'FAIL_RESOURCES_OR_EVIDENCE'
    reason = None
    maxima = cpu = server_gate = common = ids = None
    try:
        if returncode != 0:
            raise GateError('server monitor/normalization failed: ' + str(raw['stop_reasons']))
        status, maxima, cpu, server_gate, common, ids = validate_arm(root, arm, protocol, config, raw)
        if model_stat() != protocol['c19']['model_stat']:
            raise GateError('model file identity changed')
    except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
        reason = f'{type(exc).__name__}: {exc}'
    if any(reason in raw['stop_reasons'] for reason in
           ('CPU_TJMAX_100','CPU_PROCESSOR_COOLING_ACTIVE',
            'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING','THERMAL_GUARD')):
        status = 'FAIL_THERMAL_LIMIT'
    receipt = {'schema': 'c19-p12-prefix-mechanism-v1', 'run_id': run_id, 'arm': arm,
               'measurement_commit': commit, 'status': status, 'reason': reason,
               'server_returncode': returncode, 'elapsed_s': raw['elapsed_s'],
               'idle': idle, 'maxima': maxima, 'cpu_diagnostics': cpu,
               'server_gate': server_gate, 'stop_reasons': raw['stop_reasons'],
               'actual_common_prefix_ids': common,
               'token_id_sha256': {k: digest(v) for k,v in ids.items()} if ids else None,
               'results': [{'id': x['id'], 'usage': x['usage'], 'timings': x['timings'],
                            'message_sha256': digest(x['message'])} for x in raw['results']],
               'raw_sha256': sha256(raw_path), 'protocol_sha256': sha256(protocol_path),
               'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    with (root / f'{run_id}-receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
    print(json.dumps({'run_id': run_id, 'status': status, 'reason': reason,
                      'common_prefix_ids': common,
                      'second_cache_n': receipt['results'][1]['timings']['cache_n'] if len(receipt['results'])==2 else None},
                     allow_nan=False), flush=True)
    return 0 if status in ('PASS_MECHANISM','PREFIX_REUSE_NOT_OBSERVED') else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--arm', choices=ARMS)
    p.add_argument('--measurement-commit')
    args = p.parse_args()
    root = args.root.resolve()
    if args.freeze:
        for arm in ARMS:
            protocol, _, _, _ = frozen(root, arm)
            with (root / f'prefix-protocol-{arm}.json').open('x') as f:
                json.dump(protocol, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
        print('frozen P12 prefix ON protocol')
        return 0
    if not args.measurement_commit:
        p.error('measurement commit required')
    if args.arm:
        return run_arm(root, args.arm, args.measurement_commit)
    p.error('choose --arm on')


if __name__ == '__main__':
    raise SystemExit(main())
