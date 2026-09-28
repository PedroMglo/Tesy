#!/usr/bin/env python3
"""Bounded two-turn P12 server bridge with the actual first assistant answer."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, MODEL_SHA, configuration, digest, git, validate_receipt
from run_bounded import backend_library_hashes, sha256


ROOT = Path('results/c51-assistant-history-20260928T1102Z')
BACKEND = Path('/tmp/tesy-c35-backend-20260928')
BINARY = BACKEND/'build-c35-gcc15/bin/llama-server'
RUN_ID = 'c51-p12-assistant-history01'
IDS = ('c51-turn00', 'c51-turn01')


def save_new(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def input_row():
    row = strict_json((ROOT/'session-input.json').read_text())
    if row != {'schema':'c51-assistant-history-input-v1',
               'base_prefix_words':1960, 'increment_beta_words':127,
               'first_question':'\nChoose any five-digit code. Reply with the five digits only.',
               'second_question':'\nRepeat the exact text of your immediately previous answer, with no additions.',
               'template_date':'2026-09-28','max_tokens':256,
               'temperature':0,'seed':42,'context_total':8192}:
        raise GateError('C51 session input changed')
    return row


def prepare():
    if (ROOT/'protocol.json').exists():
        raise GateError('C51 top protocol no-replace')
    row = input_row()
    prior = strict_json(Path('results/c37-session-retention-20260928T0226Z/decision.json').read_text())
    failed = strict_json(Path('results/c48-skip-boundary-20260928T0954Z/decision.json').read_text())
    blocked = strict_json(Path('results/c49-assistant-history-20260928T1021Z/decision.json').read_text())
    failed_gate = strict_json(Path('results/c50-assistant-history-20260928T1042Z/decision.json').read_text())
    if prior['status'] != 'PASS_SPACED_SESSION_RETENTION' or \
       failed['status'] != 'FAIL_SAME_PROFILE_FIDELITY' or \
       blocked['status'] != 'THERMAL_PREFLIGHT_BLOCKED' or \
       failed_gate['specific_failure'] != 'PREFIX_ACCOUNTING_GATE_BOUNDED_TO_OLD_PROMPT_ONLY' or \
       not BINARY.is_file() or git('-C',str(BACKEND),'status','--porcelain'):
        raise GateError('C51 parent/source evidence invalid')
    top = {'schema':'c51-assistant-history-protocol-v1',
           'status':'FROZEN_BEFORE_MODEL',
           'objective':'verify exact-prefix retention and final-content continuity using the actual previous assistant reply in one P12 8K server session',
           'hypothesis':'fixed template date and compatible options preserve the first 2K token prefix and allow the second answer to reproduce the first five-digit code',
           'alternative':'assistant-history serialization or server cache behavior loses the prefix or answer, despite synthetic user-only retention',
           'backend_candidate_commit':git('-C',str(BACKEND),'rev-parse','HEAD'),
           'backend_tree':git('-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
           'server_binary_sha256':sha256(BINARY),
           'server_library_sha256':backend_library_hashes(str(BINARY),BACKEND),
           'model_sha256':MODEL_SHA,'model_stat':model_stat(),
           'input_sha256':sha256(ROOT/'session-input.json'),
           'runner_sha256':sha256(__file__),
           'server_runner_sha256':sha256(server.__file__),
           'parent_c37_sha256':sha256('results/c37-session-retention-20260928T0226Z/decision.json'),
           'parent_c48_sha256':sha256('results/c48-skip-boundary-20260928T0954Z/decision.json'),
           'parent_c49_sha256':sha256('results/c49-assistant-history-20260928T1021Z/decision.json'),
           'parent_c50_sha256':sha256('results/c50-assistant-history-20260928T1042Z/decision.json'),
           'server_cache_source_sha256':sha256(BACKEND/'tools/server/server-context.cpp'),
           'resource_guards':'E18 zero swap, RSS16GiB, cgroup16.5GiB, GPU6500MiB reserve, MemAvailable6GiB, CPU95 warning/100 stop, GPU80/NVMe70',
           'effective_profile':'C35 backend P12 ngl12 ub32 slots32 preload ON, full-SWA, F16 KV, n_ctx8192, exact-prefix cache, medium effort, AC performance',
           'workload':'first synthetic ~2K official-token prompt; second +127 beta words, actual first assistant content inserted; no hidden truncation',
           'primary_gate':'two complete finite API responses, first five ASCII digits, second exact same text, official prompt IDs, old input LCP>=1900 and tail<=32, cache_n in [LCP-32,min(current_prompt_len,LCP+previous_completion_tokens)]',
           'endpoint_metrics':['first_text_chunk_s','first_final_content_chunk_s','request_wall_s','decode_tok_s'],
           'run_order':list(IDS),'max_tokens':row['max_tokens'],
           'idle_admission':'300 contiguous seconds, start CPU/GPU/NVMe <=55/55/50 C; C49 <=50 CPU blocked without model',
           'timeout_s':1500,'failure_policy':'first output/cache/identity/resource failure stops; preserve raw; no retry',
           'limits':['one synthetic two-turn session only','no causal speedup or sustained 20-request assistant-history claim'],
           'default_changed':False}
    if not top['server_library_sha256']:
        raise GateError('C51 server library hashes absent')
    save_new(ROOT/'protocol.json', top)
    print(json.dumps({'status':'PREPARED','backend_commit':top['backend_candidate_commit']}))


def frozen():
    top = strict_json((ROOT/'protocol.json').read_text())
    row = input_row()
    if top['backend_candidate_commit'] != git('-C',str(BACKEND),'rev-parse','HEAD') or \
       git('-C',str(BACKEND),'status','--porcelain') or \
       sha256(BINARY) != top['server_binary_sha256'] or \
       sha256(server.__file__) != top['server_runner_sha256'] or \
       sha256(__file__) != top['runner_sha256'] or \
       sha256(BACKEND/'tools/server/server-context.cpp') != top['server_cache_source_sha256'] or \
       sha256(ROOT/'session-input.json') != top['input_sha256'] or \
       model_stat() != top['model_stat']:
        raise GateError('C51 source/model/input differs from freeze')
    protocol, config = configuration(ROOT)
    command = config['server_command']
    command[0] = str(BINARY)
    command[command.index('-ngl')+1] = '12'
    config.update(backend_root=str(BACKEND), suite='c51session',
                  task_ids=list(IDS), n_ctx=8192, pretokenize=True,
                  freeze_token_ids=True, append_previous_assistant_to_next=True,
                  allow_cache_prompt=True, enforce_output_reserve=True,
                  stream_requests=True,
                  prompt_token_ranges={IDS[0]:[1980,2150],IDS[1]:[2100,2500]},
                  adjacent_cache_min_common=None,
                  adjacent_prefix_tail_max=None,
                  request_policy={'mode':'actual-assistant-history','attempts':1,
                                  'max_tokens':row['max_tokens'],
                                  'temperature':0,'seed':42,
                                  'per_request_timeout_s':900},
                  total_timeout_s=top['timeout_s'])
    protocol['identity'].update(backend_sha=top['backend_candidate_commit'],
                                binary_sha256=sha256(BINARY),
                                library_sha256=top['server_library_sha256'],
                                config_sha256=digest(config),
                                workload_sha256=sha256(ROOT/'session-input.json'),
                                input_sha256={'session-input.json':top['input_sha256'],
                                              'protocol.json':sha256(ROOT/'protocol.json')})
    protocol.update(campaign_id='tesy-c51-assistant-history-20260928',
                    protocol_id=RUN_ID+'-v1', expected_request_ids=list(IDS))
    protocol['limits']['cpu_max_c'] = 100
    protocol['c51'] = protocol.pop('c9')
    protocol['c51'].update(mode='actual-assistant-history', n_gpu_layers=12,
                           backend_tree=top['backend_tree'],
                           runner_sha256=sha256(__file__),
                           monitor_scope='systemd user scope E18, zero swap')
    protocol['c18'] = {'thermal_monitor':'CPU95 warning, CPU100/explicit cooling/clock collapse stop',
                       'monitor_sha256':sha256(server.__file__)}
    first = 'Context: ' + 'alpha '*row['base_prefix_words'] + row['first_question']
    second = ' beta'*row['increment_beta_words'] + row['second_question']
    tasks = [(IDS[0], {'id':IDS[0],'category':'synthetic-assistant-history',
                       'messages':[{'role':'user','content':first}], 'cache_prompt':True,
                       'chat_template_kwargs':{'tesy_template_date':row['template_date']}}),
             (IDS[1], {'id':IDS[1],'category':'synthetic-assistant-history',
                       'messages':[{'role':'user','content':second}], 'cache_prompt':True,
                       'chat_template_kwargs':{'tesy_template_date':row['template_date']}})]
    return protocol, config, tasks


def validate(protocol, config, raw):
    samples = [strict_json(line) for line in
               (ROOT/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    maxima = validate_receipt(protocol, config, raw, samples, ROOT,
                              run_id=RUN_ID, protocol_filename=f'protocols/{RUN_ID}.json',
                              expected_results=2)
    cpu = summarize_samples(samples, require_safe=True)
    ids = strict_json((ROOT/'raw'/f'{RUN_ID}.tokenization.json').read_text())
    if list(ids) != list(IDS) or [r['id'] for r in raw['results']] != list(IDS):
        raise GateError('C51 request/token identities incomplete')
    first, second = raw['results']
    for item, name in zip((first,second), IDS):
        usage, stream = item.get('usage'), item.get('stream_metrics')
        if type(usage) is not dict or usage.get('prompt_tokens') != len(ids[name]) or \
           type(usage.get('completion_tokens')) is not int or \
           not 0 < usage['completion_tokens'] < 256 or \
           item.get('finish_reason') != 'stop' or type(stream) is not dict or \
           stream.get('done_observed') is not True or \
           type(stream.get('first_final_content_chunk_s')) not in (int,float):
            raise GateError('C51 output count/final-content/completion incomplete')
    first_content = first['message'].get('content')
    second_content = second['message'].get('content')
    if type(first_content) is not str or not re.fullmatch(r'[0-9]{5}',first_content.strip()) or \
       second_content != first_content:
        raise GateError('C51 actual assistant-history answer not reproduced exactly')
    a, b = ids[IDS[0]], ids[IDS[1]]
    common = next((i for i, (left, right) in enumerate(zip(a, b)) if left != right),
                  min(len(a), len(b)))
    cache_n = second['timings']['cache_n']
    bound = min(len(b), common + first['usage']['completion_tokens'])
    if common < 1900 or len(a) - common > 32 or \
       type(cache_n) is not int or not common - 32 <= cache_n <= bound or \
       second['timings']['prompt_n'] + cache_n != len(b):
        raise GateError('C51 source-bounded generated-token prefix cache outside frozen band')
    return maxima, cpu, common, ids


def run(commit):
    if git('rev-parse','HEAD') != commit or git('status','--porcelain'):
        raise GateError('C51 measurement commit/worktree not frozen')
    idle_total = sum(strict_json(path.read_text())['duration_s']
                     for path in Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed() + idle_total + 2400 + 2400 > 16*3600:
        raise GateError('C51 physical budget cannot cover run/cleanup')
    protocol, config, tasks = frozen()
    path = ROOT/'protocols'/f'{RUN_ID}.json'
    pre = strict_json((ROOT/'preflight.json').read_text())
    if strict_json(path.read_text()) != protocol or \
       pre['guard_status'] != 'READY_FOR_IDLE_ADMISSION' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip() != pre['power_profile']:
        raise GateError('C51 preflight/protocol/power changed')
    scope = check_scope(); no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('C51 cooling active before idle')
    idle = thermal_idle(ROOT,RUN_ID,match_tolerance_c=(5,5,3),max_start_c=(55,55,50))
    save_new(ROOT/f'{RUN_ID}-idle.json',idle)
    receipt = {'schema':'c51-assistant-history-receipt-v1','run_id':RUN_ID,
               'measurement_commit':commit,'status':'THERMAL_PREFLIGHT_BLOCKED',
               'idle':idle,'default_changed':False}
    if idle['status'] != 'PASS':
        save_new(ROOT/f'{RUN_ID}-receipt.json',receipt);return 2
    if check_scope() != scope or cpu_capture()['processor_cooling_max_state'] or \
       model_stat() != protocol['c51']['model_stat']:
        raise GateError('C51 scope/cooling/model changed after idle')
    no_other_model()
    args = SimpleNamespace(model='target120b',suite='c51session',run_id=RUN_ID,protocol=path)
    try:
        rc = server.run(args,protocol,config,tasks,MODEL)
        launch_error = None
    except (GateError,OSError,RuntimeError,ValueError) as exc:
        rc = 1; launch_error = f'{type(exc).__name__}: {exc}'
    raw_path = ROOT/'raw'/f'{RUN_ID}.json'
    receipt.update(status='FAIL_RESOURCES_OR_EVIDENCE',runner_returncode=rc,
                   launch_error=launch_error,
                   protocol_sha256=sha256(path),
                   raw_sha256=sha256(raw_path) if raw_path.exists() else None)
    if raw_path.exists():
        raw = strict_json(raw_path.read_text())
        receipt.update(returncode=raw['returncode'],stop_reasons=raw['stop_reasons'],
                       elapsed_s=raw['elapsed_s'],completed_requests=len(raw['results']))
        if rc == 0:
            try:
                maxima,cpu,common,ids = validate(protocol,config,raw)
                receipt.update(status='PASS_ASSISTANT_HISTORY_TESTED_SCOPE',
                               maxima=maxima,cpu_diagnostics=cpu,
                               common_prefix_ids=common,
                               token_id_sha256={name:digest(ids[name]) for name in IDS},
                               results=[{'id':x['id'],'usage':x['usage'],
                                         'timings':x['timings'],
                                         'request_elapsed_s':x['ended_s']-x['started_s'],
                                         'stream_metrics':x['stream_metrics'],
                                         'message_sha256':digest(x['message'])}
                                        for x in raw['results']])
            except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                receipt['reason'] = f'{type(exc).__name__}: {exc}'
    save_new(ROOT/f'{RUN_ID}-receipt.json',receipt)
    print(json.dumps({'status':receipt['status'],'completed':receipt.get('completed_requests'),
                      'elapsed_s':receipt.get('elapsed_s'),'reason':receipt.get('reason')},
                     allow_nan=False),flush=True)
    return 0 if receipt['status'] == 'PASS_ASSISTANT_HISTORY_TESTED_SCOPE' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true')
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--run',action='store_true')
    parser.add_argument('--measurement-commit')
    args = parser.parse_args()
    if args.root != ROOT or not (ROOT/'raw').is_dir() or not (ROOT/'protocols').is_dir():
        raise GateError('C51 root differs')
    if args.prepare:
        prepare(); return 0
    if args.freeze:
        protocol,_,_ = frozen()
        save_new(ROOT/'protocols'/f'{RUN_ID}.json',protocol)
        print(json.dumps({'status':'FROZEN','protocol_sha256':sha256(ROOT/'protocols'/f'{RUN_ID}.json')}))
        return 0
    if not args.measurement_commit:
        parser.error('--measurement-commit required')
    return run(args.measurement_commit)


if __name__ == '__main__':
    raise SystemExit(main())
