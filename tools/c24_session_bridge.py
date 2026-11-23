#!/usr/bin/env python3
"""Bounded streaming 8K server bridge for a 2048+128 exact-prefix request."""

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

SPEC = (('c24-g1-prefix2048','on','G1',1),)
SPEC_BY_ID = {item[0]:item for item in SPEC}
REQUESTS = ('c24-prefix2048', 'c24-increment128')
C17_ROOT = Path('results/c17-thermal-recovery-20260927T1656Z')
C18_ROOT = Path('results/c18-cpu100-retest-20260927T1756Z')
C19_ROOT = Path('results/c19-prefix-20260927T1842Z')
C20_ROOT = Path('results/c20-prefix-pairs-20260927T1857Z')
C21_ROOT = Path('results/c21-prefix-pairs-20260927T1927Z')
C22_ROOT = Path('results/c22-prefix-pairs-20260927T1937Z')
C23_ROOT = Path('results/c23-prefix-confirm-20260927T2027Z')


def require_output_root(root):
    raw = root / 'raw'
    if not raw.is_dir() or not raw.resolve().is_relative_to(root.resolve()):
        raise GateError('C24 raw output directory missing or escapes campaign root')
    return raw


def workload(root):
    row = strict_json((root / 'bridge-input.json').read_text())
    if row != {'schema':'c24-bridge-input-v1',
               'context_intro':'Context: ', 'prefix_words':1960,
               'increment_words':128, 'question':'\nReply with exactly OK.',
               'max_tokens':256, 'first_prompt_range':[1980,2100],
               'second_prompt_range':[2108,2228],
               'min_common_prefix_ids':1900}:
        raise GateError('C24 frozen bridge input changed')
    return row


def prompt_text(row, increment_words):
    return row['context_intro'] + 'alpha '*row['prefix_words'] + \
           ' beta'*increment_words + row['question']


def frozen(root, spec):
    run_id, arm, phase, order = spec
    protocol, config = configuration(root)
    command = config['server_command']
    if command[command.index('-ngl')+1] != '8' or command[command.index('-ub')+1] != '32':
        raise GateError('expected P8/ub32 server base changed')
    command[command.index('-ngl')+1] = '12'
    row = workload(root)
    config.update({'suite': 'c24bridge', 'arm': arm,
                   'task_ids': list(REQUESTS), 'n_ctx': 8192,
                   'pretokenize': True, 'freeze_token_ids': True,
                   'allow_cache_prompt': True, 'enforce_output_reserve': True,
                   'prompt_token_ranges': {
                       REQUESTS[0]: row['first_prompt_range'],
                       REQUESTS[1]: row['second_prompt_range']},
                   'token_id_relationships': [{'first':REQUESTS[0],
                                               'second':REQUESTS[1],
                                               'expected_delta':128,
                                               'min_common':row['min_common_prefix_ids']}],
                   'stream_requests': True,
                   'request_policy': {'mode': 'synthetic-streaming-session-bridge',
                                      'attempts': 1, 'max_tokens': 256,
                                      'temperature': 0, 'seed': 42,
                                      'per_request_timeout_s': 900},
                   'total_timeout_s': 1800})
    prior = strict_json((C23_ROOT / 'raw/c23-p3-on.preflight.json').read_text())['config']
    common = {'server_command', 'explicit_env', 'n_ctx', 'pretokenize',
              'freeze_token_ids', 'allow_cache_prompt', 'enforce_output_reserve'}
    contract = strict_json((root / 'usage-contract.json').read_text())
    if {key: config[key] for key in common} != {key: prior[key] for key in common} or \
            contract != {'schema':'c24-8k-bridge-contract-v1','n_ctx':8192,
                         'n_batch':256,'n_ubatch':32,'slots':32,
                         'reasoning_effort':'medium','output_cap':256,
                         'prefix_target_tokens':2048,'increment_tokens':128,
                         'no_context_shift':True,'swa_full':True}:
        raise GateError('C24 effective server profile or usage contract changed')
    prior_protocol = strict_json((C23_ROOT/'protocols/c23-p3-on.json').read_text())
    if any(protocol['identity'][key] != prior_protocol['identity'][key] for key in
           ('model_sha256','backend_sha','binary_sha256','library_sha256')):
        raise GateError('C24 model/backend/binary/library differs from C23')
    protocol['campaign_id'] = 'tesy-c24-session-bridge-20260927'
    protocol['protocol_id'] = run_id + '-v1'
    protocol['expected_request_ids'] = list(REQUESTS)
    protocol['identity']['config_sha256'] = digest(config)
    protocol['identity']['workload_sha256'] = sha256(root / 'bridge-input.json')
    protocol['identity']['input_sha256'] = {
        'bridge-input.json': sha256(root / 'bridge-input.json'),
        'usage-contract.json': sha256(root / 'usage-contract.json')}
    protocol['limits']['cpu_max_c'] = 100
    protocol['c24'] = protocol.pop('c9')
    protocol['c24'].update(mode='synthetic-streaming-2048-prefix-bridge', n_gpu_layers=12,
                           arm=arm, phase=phase, order=order,
                           prefix_runner_sha256=sha256(__file__),
                           parent_C20_decision_sha256=sha256(C20_ROOT / 'decision.json'),
                           parent_C21_decision_sha256=sha256(C21_ROOT / 'decision.json'),
                           parent_C22_decision_sha256=sha256(C22_ROOT / 'decision.json'),
                           parent_C23_decision_sha256=sha256(C23_ROOT / 'decision.json'),
                           idle_max_start_c=[50, 50, 45],
                           idle_match_tolerance_c=[5, 5, 3],
                           claim='one bounded 2048+128 synthetic streaming bridge; no full M3/M4/quality claim')
    protocol['c18'] = {'thermal_monitor':'CPU95 warning, CPU100/explicit cooling/clock collapse stop',
                       'monitor_sha256':sha256(server.__file__)}
    messages1 = [{'role': 'user', 'content': prompt_text(row, 0)}]
    messages2 = [{'role': 'user', 'content': prompt_text(row, row['increment_words'])}]
    tasks = [(REQUESTS[0], {'id': REQUESTS[0], 'category': 'synthetic-session-bridge',
                            'messages': messages1, 'cache_prompt': True}),
             (REQUESTS[1], {'id': REQUESTS[1], 'category': 'synthetic-session-bridge',
                            'messages': messages2, 'cache_prompt': True})]
    return protocol, config, tasks, row


def validate_arm(root, spec, protocol, config, raw):
    run_id, arm, phase, order = spec
    samples = [strict_json(line) for line in
               (root / 'raw' / f'{run_id}.samples.jsonl').read_text().splitlines()]
    maxima = validate_receipt(protocol, config, raw, samples, root,
                              run_id=run_id, protocol_filename=f'protocols/{run_id}.json',
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
    row = workload(root)
    if len(ids[REQUESTS[1]]) - len(ids[REQUESTS[0]]) != 128 or \
       common < row['min_common_prefix_ids']:
        raise GateError('tokenized common prefix below frozen minimum')
    results = raw['results']
    first, second = (x['timings'] for x in results)
    if first['cache_n'] != 0 or any(x['usage']['prompt_tokens'] != len(ids[x['id']]) for x in results):
        raise GateError('first request cache or official token counts invalid')
    if any(x['usage']['completion_tokens'] <= 0 or
           x['usage']['completion_tokens'] > row['max_tokens'] for x in results):
        raise GateError('completion count outside frozen cap')
    if second['cache_n'] > common or second['cache_n'] < common - 32:
        raise GateError('cache reuse outside frozen common-prefix band')
    for item in results:
        stream = item.get('stream_metrics')
        if type(stream) is not dict or stream.get('done_observed') is not True or \
           type(stream.get('sse_event_count')) is not int or stream['sse_event_count'] < 2 or \
           type(stream.get('first_text_chunk_s')) not in (int, float) or \
           not 0 < stream['first_text_chunk_s'] <= item['ended_s']-item['started_s']:
            raise GateError('stream text/completion fence incomplete')
        first_final = stream.get('first_final_content_chunk_s')
        if first_final is not None and (type(first_final) not in (int, float) or
                                        not stream['first_text_chunk_s'] <= first_final <=
                                        item['ended_s']-item['started_s']):
            raise GateError('first final content timestamp invalid')
    status = 'PASS_BRIDGE'
    return status, maxima, cpu, server_gate, common, ids


def run_arm(root, spec, commit):
    run_id, arm, phase, order = spec
    protocol_path = root / 'protocols' / f'{run_id}.json'
    protocol, config, tasks, _ = frozen(root, spec)
    require_output_root(root)
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or \
       strict_json(protocol_path.read_text()) != protocol or \
       model_stat() != protocol['c24']['model_stat']:
        raise GateError('prefix arm differs from frozen commit/identity')
    previous_idle_s = 394.4515725659985
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C17_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C18_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C19_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C20_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C21_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C22_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           C23_ROOT.glob('*-idle.json'))
    previous_idle_s += sum(strict_json(p.read_text())['duration_s'] for p in
                           root.glob('*-idle.json'))
    if program_physical_consumed() + previous_idle_s + 900 + 1850 > 16*3600:
        raise GateError('physical time budget cannot cover C24 bridge')
    if strict_json((C19_ROOT/'decision.json').read_text())['status'] != 'PREFIX_REUSE_OBSERVED':
        raise GateError('C19 ON mechanism did not pass')
    if strict_json((C20_ROOT/'decision.json').read_text())['status'] != 'THERMAL_PREFLIGHT_BLOCKED':
        raise GateError('C20 incomplete pair provenance changed')
    if strict_json((C21_ROOT/'decision.json').read_text())['status'] != 'FAIL_HARNESS_PRELAUNCH':
        raise GateError('C21 prelaunch failure provenance changed')
    if strict_json((C22_ROOT/'decision.json').read_text())['status'] != 'SCREEN_GO_CONFIRMATION_REQUIRED':
        raise GateError('C22 screen GO provenance changed')
    if strict_json((C23_ROOT/'decision.json').read_text())['status'] != 'CONFIRMED_PREFIX_SYNTHETIC_SCOPE':
        raise GateError('C23 confirmation provenance changed')
    preflight = strict_json((root/'preflight.json').read_text())
    if preflight['guard_status'] != 'READY_FOR_IDLE_ADMISSION' or \
       preflight['power_source'] != 'AC' or \
       Path('/sys/class/power_supply/AC0/online').read_text().strip() != '1' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip() != preflight['power_profile']:
        raise GateError('C24 host/power preflight changed')
    scope = check_scope()
    no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('processor cooling active before C24 idle')
    idle = thermal_idle(root, run_id, match_tolerance_c=(5, 5, 3),
                        max_start_c=(50, 50, 45))
    with (root / f'{run_id}-idle.json').open('x') as out:
        json.dump(idle,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    if idle['status'] != 'PASS':
        receipt = {'schema':'c24-prefix-receipt-v1','run_id':run_id,
                   'measurement_commit':commit,'status':'THERMAL_PREFLIGHT_BLOCKED',
                   'idle':idle,'model_runs':0,'default_changed':False}
        with (root/f'{run_id}-receipt.json').open('x') as out:
            json.dump(receipt,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        return 2
    if run_id == SPEC[0][0]:
        with (root/'baseline.json').open('x') as out:
            json.dump({'cpu_c':idle['end']['cpu_c'],
                       'gpu_c':idle['end']['gpu']['temperature_c'],
                       'nvme_c':idle['end']['nvme_c']},out,indent=2,allow_nan=False)
            out.write('\n')
    if check_scope() != scope or cpu_capture()['processor_cooling_max_state'] or \
       Path('/sys/class/power_supply/AC0/online').read_text().strip() != '1' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip() != preflight['power_profile']:
        raise GateError('scope/CPU mitigation/power profile changed after C24 idle')
    no_other_model()
    args_c2 = SimpleNamespace(model='target120b', suite='c24bridge', run_id=run_id,
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
        status, maxima, cpu, server_gate, common, ids = validate_arm(root, spec, protocol, config, raw)
        if model_stat() != protocol['c24']['model_stat']:
            raise GateError('model file identity changed')
    except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
        reason = f'{type(exc).__name__}: {exc}'
    if any(reason in raw['stop_reasons'] for reason in
           ('CPU_TJMAX_100','CPU_PROCESSOR_COOLING_ACTIVE',
            'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING','THERMAL_GUARD')):
        status = 'FAIL_THERMAL_LIMIT'
    receipt = {'schema': 'c24-p12-streaming-session-bridge-v1', 'run_id': run_id,
               'arm': arm, 'phase':phase, 'order':order,
               'measurement_commit': commit, 'status': status, 'reason': reason,
               'server_returncode': returncode, 'elapsed_s': raw['elapsed_s'],
               'idle': idle, 'maxima': maxima, 'cpu_diagnostics': cpu,
               'server_gate': server_gate, 'stop_reasons': raw['stop_reasons'],
               'actual_common_prefix_ids': common,
               'token_id_sha256': {k: digest(v) for k,v in ids.items()} if ids else None,
               'results': [{'id': x['id'], 'usage': x['usage'], 'timings': x['timings'],
                            'stream_metrics': x.get('stream_metrics'),
                            'request_elapsed_s':x['ended_s']-x['started_s'],
                            'message_sha256': digest(x['message'])} for x in raw['results']],
               'raw_sha256': sha256(raw_path), 'protocol_sha256': sha256(protocol_path),
               'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    with (root / f'{run_id}-receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
    print(json.dumps({'run_id': run_id, 'status': status, 'reason': reason,
                      'common_prefix_ids': common,
                      'second_cache_n': receipt['results'][1]['timings']['cache_n'] if len(receipt['results'])==2 else None},
                     allow_nan=False), flush=True)
    return 0 if status == 'PASS_BRIDGE' else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--run', choices=SPEC_BY_ID)
    p.add_argument('--measurement-commit')
    args = p.parse_args()
    root = args.root.resolve()
    if args.freeze:
        (root/'raw').mkdir(exist_ok=False)
        require_output_root(root)
        (root/'protocols').mkdir(exist_ok=False)
        for spec in SPEC:
            protocol, _, _, _ = frozen(root, spec)
            with (root / 'protocols' / f'{spec[0]}.json').open('x') as f:
                json.dump(protocol, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
        print('frozen C24 2048+128 streaming bridge protocol')
        return 0
    if not args.measurement_commit:
        p.error('measurement commit required')
    if args.run:
        return run_arm(root, SPEC_BY_ID[args.run], args.measurement_commit)
    p.error('choose --run')


if __name__ == '__main__':
    raise SystemExit(main())
