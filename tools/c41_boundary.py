#!/usr/bin/env python3
"""One bounded P12 7936+256 synthetic retrieval at the 8K server boundary."""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import tiktoken

import c2_server_run as server
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c8_observer_runner import program_physical_consumed
from c9_server_admission import digest, git, validate_receipt
import c38_quality_run as base
from run_bounded import sha256, gpu_state, mem_available, thermal_state


ROOT = Path('results/c41-8k-boundary-20260928T0715Z')
RUN_ID = 'c41-p12-boundary7936'
PARENT = Path('results/c40-quality-recovery-20260928T0528Z/decision.json')
C37_TOKENS = Path('results/c37-session-retention-20260928T0226Z/raw/c37-spaced20-prefix.tokenization.json')


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def input_text(root):
    row = strict_json((root / 'input.json').read_text())
    if row['schema'] != 'c41-boundary-input-v1' or row['filler_repetitions'] != 7833 or \
       row['official_prompt_token_count_required'] != 7936 or row['max_output_tokens'] != 256 or \
       row['n_ctx'] != 8192 or row['expected_answer'] != 'Q7M2N9' or \
       row['template_date'] != '2026-09-28' or row['reasoning_effort'] != 'medium':
        raise GateError('C41 input contract changed')
    prompt = row['first_line'] + row['filler_word'] * row['filler_repetitions'] + row['last_line']
    if hashlib.sha256(prompt.encode()).hexdigest() != row['prompt_sha256']:
        raise GateError('C41 prompt bytes differ')
    return row, prompt


def tokenizer_bridge(root):
    row, prompt = input_text(root)
    encoding = tiktoken.get_encoding('o200k_base')
    plain_ids = encoding.encode(prompt)
    if len(plain_ids) != row['prompt_plain_token_count_o200k'] or \
       len(plain_ids) + row['template_token_overhead_from_c37'] != 7936:
        raise GateError('C41 model-free prompt count differs')
    historic = strict_json(C37_TOKENS.read_text())['c37-request-00']
    historic_text = 'Context: ' + 'alpha ' * 1960 + '\nReply with exactly OK.'
    historic_ids = encoding.encode(historic_text)
    if len(historic) != 2035 or historic[64:64+len(historic_ids)] != historic_ids or \
       len(historic) - len(historic_ids) != 67:
        raise GateError('C41 o200k/official-template bridge not reproduced')
    mutant = row['first_line'] + row['filler_word'] * (row['filler_repetitions']-1) + row['last_line']
    if len(encoding.encode(mutant)) + 67 == 7936:
        raise GateError('C41 off-by-one mutant did not discriminate')
    return {'status': 'PASS', 'plain_tokens': len(plain_ids),
            'inferred_template_overhead': 67, 'expected_official_tokens': 7936,
            'historical_bridge': str(C37_TOKENS), 'off_by_one_mutant_rejected': True}


def specs(root):
    top = strict_json((root / 'protocol.json').read_text())
    row, prompt = input_text(root)
    if top['schema'] != 'c41-8k-boundary-protocol-v1' or \
       top['run_id'] != RUN_ID or top['parent_c40_decision_sha256'] != sha256(PARENT) or \
       top['input_sha256'] != sha256(root / 'input.json') or \
       top['runner_sha256'] != sha256(__file__) or \
       git('-C', str(base.TARGET_BACKEND), 'status', '--porcelain'):
        raise GateError('C41 source/parent/input freeze differs')
    protocol, config, _, model = base.get_specs(root, 'p12')
    task = {'id': RUN_ID, 'category': 'synthetic-long-context-retrieval',
            'messages': [{'role': 'user', 'content': prompt}],
            'cache_prompt': False,
            'chat_template_kwargs': {'tesy_template_date': row['template_date'],
                                     'reasoning_effort': row['reasoning_effort']}}
    config.update(suite='c41boundary', task_ids=[RUN_ID], n_ctx=8192,
                  pretokenize=True, freeze_token_ids=True,
                  prompt_token_ranges={RUN_ID: [7936, 7936]},
                  enforce_output_reserve=True, allow_cache_prompt=False,
                  stream_requests=True, total_timeout_s=top['timeout_s'],
                  request_policy={'mode': '8k-synthetic-retrieval', 'attempts': 1,
                                  'max_tokens': 256, 'temperature': 0, 'seed': 42,
                                  'reasoning_effort': 'medium',
                                  'per_request_timeout_s': 2400})
    protocol['identity']['config_sha256'] = digest(config)
    protocol['identity']['workload_sha256'] = sha256(root / 'input.json')
    protocol['identity']['input_sha256'] = {'input.json': sha256(root / 'input.json'),
                                             'protocol.json': sha256(root / 'protocol.json'),
                                             'c40-decision.json': sha256(PARENT)}
    protocol.update(campaign_id=top['campaign_id'], protocol_id=RUN_ID+'-v1',
                    expected_request_ids=[RUN_ID])
    protocol['limits']['cpu_max_c'] = 100
    protocol['c41'] = protocol.pop('c38')
    protocol['c41'].update(mode='one-8k-boundary-retrieval', n_gpu_layers=12,
                           runner_sha256=sha256(__file__),
                           prompt_sha256=row['prompt_sha256'],
                           expected_official_prompt_tokens=7936,
                           parent_c40_decision_sha256=sha256(PARENT),
                           claim=top['claim_if_pass'])
    return protocol, config, [(RUN_ID, task)], model


def budget():
    idle = sum(strict_json(path.read_text())['duration_s']
               for path in Path('results').glob('c*-*/**/*-idle.json'))
    interrupted = strict_json(Path('results/c39-quality-recovery-20260928T0438Z/interruption.json').read_text())['physical_runtime_charged_s']
    if program_physical_consumed() + idle + interrupted + 3000 + 900 > 16*3600:
        raise GateError('C41 remaining physical budget insufficient for run and cleanup')


def preflight(root):
    tokenizer_bridge(root)
    protocol, config, _, model = specs(root)
    no_other_model()
    if mem_available() < 6*2**30 or not gpu_state() or not thermal_state() or \
       cpu_capture()['processor_cooling_max_state']:
        raise GateError('C41 host preflight failed')
    budget()
    row = {'schema': 'c41-preflight-v1', 'status': 'READY',
           'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'power_profile': subprocess.check_output(['powerprofilesctl','get'], text=True).strip(),
           'gpu': gpu_state(), 'thermal': thermal_state(),
           'mem_available_bytes': mem_available(),
           'model_stat': base.stat(model),
           'backend_commit': git('-C', str(base.TARGET_BACKEND), 'rev-parse', 'HEAD'),
           'protocol_sha256': digest(protocol),
           'config_sha256': digest(config),
           'tokenizer_bridge': tokenizer_bridge(root)}
    save_new(root / 'preflight.json', row)
    print(json.dumps({'status': 'READY', 'tokenizer_bridge': row['tokenizer_bridge']}))


def run(root, commit):
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain'):
        raise GateError('C41 measurement worktree not frozen')
    budget()
    protocol, config, tasks, model = specs(root)
    if strict_json((root / 'protocols' / f'{RUN_ID}.json').read_text()) != protocol or \
       base.stat(model) != protocol['c41']['model_stat'] or \
       strict_json((root / 'preflight.json').read_text())['status'] != 'READY' or \
       subprocess.check_output(['powerprofilesctl','get'], text=True).strip() != \
       strict_json((root / 'preflight.json').read_text())['power_profile']:
        raise GateError('C41 preflight/protocol/model changed')
    check_scope(); no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('C41 processor cooling active before idle')
    idle = thermal_idle(root, RUN_ID, match_tolerance_c=(5,5,3), max_start_c=(50,50,45))
    save_new(root / f'{RUN_ID}-idle.json', idle)
    receipt = {'schema': 'c41-boundary-receipt-v1', 'run_id': RUN_ID,
               'measurement_commit': commit, 'idle': idle,
               'status': 'THERMAL_PREFLIGHT_BLOCKED', 'completed_requests': 0,
               'default_changed': False}
    if idle['status'] != 'PASS':
        save_new(root / f'{RUN_ID}-receipt.json', receipt)
        return 2
    check_scope(); no_other_model()
    args = SimpleNamespace(model='target120b', suite=config['suite'], run_id=RUN_ID,
                           protocol=root / 'protocols' / f'{RUN_ID}.json')
    try:
        rc = server.run(args, protocol, config, tasks, model)
        launch_error = None
    except (GateError, OSError, RuntimeError, ValueError) as exc:
        rc = 1
        launch_error = f'{type(exc).__name__}: {exc}'
    raw_path = root / 'raw' / f'{RUN_ID}.json'
    receipt.update(status='FAIL_RESOURCES_OR_EVIDENCE', runner_returncode=rc,
                   launch_error=launch_error,
                   raw_sha256=sha256(raw_path) if raw_path.exists() else None)
    if raw_path.exists():
        raw = strict_json(raw_path.read_text())
        receipt.update(returncode=raw['returncode'], stop_reasons=raw['stop_reasons'],
                       elapsed_s=raw['elapsed_s'], completed_requests=len(raw['results']))
        thermal = {'CPU_TJMAX_100', 'CPU_PROCESSOR_COOLING_ACTIVE',
                   'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING', 'THERMAL_GUARD'}
        if any(reason in thermal for reason in raw['stop_reasons']):
            receipt['status'] = 'FAIL_THERMAL_LIMIT'
        elif rc == 0:
            try:
                samples = [strict_json(line) for line in
                           (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
                maxima = validate_receipt(protocol, config, raw, samples, root,
                                          run_id=RUN_ID,
                                          protocol_filename=f'protocols/{RUN_ID}.json',
                                          expected_results=1)
                cpu = summarize_samples(samples, require_safe=True)
                normalized = strict_json((root/'raw'/f'{RUN_ID}.normalized.json').read_text())
                gate = validate_c2(normalized, {name: protocol[name] for name in PROTOCOL})
                token_ids = strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())[RUN_ID]
                item = raw['results'][0]
                usage = item['usage']
                if len(token_ids) != 7936 or usage['prompt_tokens'] != 7936 or \
                   not 0 < usage['completion_tokens'] <= 256 or usage['total_tokens'] > 8192 or \
                   item['timings']['cache_n'] != 0 or \
                   item['stream_metrics']['done_observed'] is not True:
                    raise GateError('C41 official tokens/reserve/cache/fence differ')
                answer = item['message'].get('content')
                receipt.update(status='PASS_BOUNDARY_RETRIEVAL' if
                               item['finish_reason'] == 'stop' and
                               isinstance(answer, str) and answer.strip() == 'Q7M2N9'
                               else 'FAIL_RETRIEVAL_OR_TRUNCATION',
                               maxima=maxima, cpu_diagnostics=cpu, server_gate=gate,
                               official_prompt_token_count=len(token_ids),
                               prompt_token_ids_sha256=digest(token_ids),
                               completion_tokens=usage['completion_tokens'],
                               total_tokens=usage['total_tokens'],
                               finish_reason=item['finish_reason'],
                               answer_sha256=digest(answer),
                               answer_matches= isinstance(answer,str) and answer.strip() == 'Q7M2N9',
                               request_wall_s=item['ended_s']-item['started_s'],
                               timings=item['timings'],
                               first_final_content_s=item['stream_metrics'].get('first_final_content_chunk_s'))
            except (GateError, KeyError, TypeError, ValueError, OSError) as exc:
                receipt['reason'] = f'{type(exc).__name__}: {exc}'
    save_new(root / f'{RUN_ID}-receipt.json', receipt)
    print(json.dumps({'run_id': RUN_ID, 'status': receipt['status'],
                      'completed': receipt['completed_requests'],
                      'reason': receipt.get('reason')}, allow_nan=False))
    return 0 if receipt['status'] == 'PASS_BOUNDARY_RETRIEVAL' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--measurement-commit')
    args = parser.parse_args()
    if args.root != ROOT or not (ROOT/'raw').is_dir() or not (ROOT/'protocols').is_dir():
        raise GateError('C41 output root differs')
    if args.freeze:
        bridge = tokenizer_bridge(ROOT)
        protocol, _, _, _ = specs(ROOT)
        save_new(ROOT/'protocols'/f'{RUN_ID}.json', protocol)
        save_new(ROOT/'model-free-tests.json', bridge)
        print(json.dumps({'status': 'FROZEN', 'protocol_sha256': sha256(ROOT/'protocols'/f'{RUN_ID}.json')}))
        return 0
    if args.preflight:
        preflight(ROOT)
        return 0
    if not args.measurement_commit:
        parser.error('--measurement-commit required')
    return run(ROOT, args.measurement_commit)


if __name__ == '__main__':
    raise SystemExit(main())
