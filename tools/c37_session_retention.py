#!/usr/bin/env python3
"""Twenty-request spaced exact-prefix retention under bounded P12 serving."""

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from statistics import median

import c2_server_run as server
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, MODEL_SHA, configuration, digest, git, validate_receipt
from run_bounded import backend_library_hashes, sha256


ROOT=Path('results/c37-session-retention-20260928T0226Z')
BACKEND=Path('/tmp/tesy-c35-backend-20260928')
BINARY=BACKEND/'build-c35-gcc15/bin/llama-server'
RUN_ID='c37-spaced20-prefix'


def save_new(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')


def workload(root):
    row=strict_json((root/'session-input.json').read_text())
    if row!={'schema':'c37-session-input-v1','base_prefix_words':1960,
             'increment_beta_words_per_request':127,'requests':20,
             'context_intro':'Context: ','question':'\nReply with exactly OK.',
             'template_date':'2026-09-28','max_tokens':64,
             'temperature':0,'seed':42,'inter_request_idle_s':180,
             'first_prompt_range':[1980,2100],'last_prompt_range':[4300,4700]}:
        raise GateError('C37 synthetic session input changed')
    return row


def overall(root):
    top=strict_json((root/'protocol.json').read_text())
    if top['schema']!='c37-session-retention-protocol-v1' or \
            top['source_parent_decision_sha256']!=sha256('results/c36c-prefix4096-20260928T0203Z/decision.json') or \
            top['backend_commit']!=git('-C',str(BACKEND),'rev-parse','HEAD') or \
            git('-C',str(BACKEND),'status','--porcelain') or \
            any(sha256(root/name)!=value for name,value in top['input_sha256'].items()) or \
            model_stat()!=strict_json((root/'preflight.json').read_text())['model']['stat']:
        raise GateError('C37 frozen source/input/model identity changed')
    return top


def frozen(root):
    top=overall(root);row=workload(root)
    protocol,config=configuration(root)
    command=config['server_command']
    if command[command.index('-ngl')+1]!='8':
        raise GateError('C37 P8 base configuration changed')
    command[0]=str(BINARY)
    command[command.index('-ngl')+1]='12'
    ids=[f'c37-request-{i:02d}' for i in range(row['requests'])]
    config.update(backend_root=str(BACKEND),suite='c37session',
                  task_ids=ids,n_ctx=8192,pretokenize=True,
                  freeze_token_ids=True,allow_cache_prompt=True,
                  enforce_output_reserve=True,stream_requests=True,
                  prompt_token_ranges={key:[max(1,1980+120*i),2100+135*i]
                                       for i,key in enumerate(ids)},
                  token_id_relationships=[],
                  inter_request_idle_s=row['inter_request_idle_s'],
                  adjacent_cache_min_common=1900,
                  adjacent_prefix_tail_max=32,
                  request_policy={'mode':'spaced-session-retention','attempts':1,
                                  'max_tokens':row['max_tokens'],
                                  'temperature':row['temperature'],'seed':row['seed'],
                                  'per_request_timeout_s':900},
                  total_timeout_s=top['time_budget_s']['server'])
    libraries=backend_library_hashes(str(BINARY),BACKEND)
    if not libraries:
        raise GateError('C37 backend libraries unavailable')
    protocol['identity'].update(backend_sha=top['backend_commit'],
                                binary_sha256=sha256(BINARY),
                                library_sha256=libraries,
                                config_sha256=digest(config),
                                workload_sha256=sha256(root/'session-input.json'),
                                input_sha256=dict(top['input_sha256'],
                                                  **{'protocol.json':sha256(root/'protocol.json')}))
    protocol.update(campaign_id='tesy-c37-session-retention-20260928',
                    protocol_id=RUN_ID+'-v1',expected_request_ids=ids)
    protocol['limits']['cpu_max_c']=100
    protocol['c37']=protocol.pop('c9')
    protocol['c37'].update(mode='spaced-session-retention',n_gpu_layers=12,
                           backend_tree=git('-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
                           runner_sha256=sha256(__file__),
                           idle_max_start_c=[50,50,45],
                           monitor_scope='systemd user scope E18, zero swap',
                           claim='one 20-request/60-minute synthetic prefix retention and resource regime')
    protocol['c18']={'thermal_monitor':'CPU95 warning, CPU100/explicit cooling/clock collapse stop',
                     'monitor_sha256':sha256(server.__file__)}
    tasks=[]
    for i,key in enumerate(ids):
        prompt=(row['context_intro']+'alpha '*row['base_prefix_words']+
                ' beta'*(row['increment_beta_words_per_request']*i)+row['question'])
        tasks.append((key,{'id':key,'category':'synthetic-session-retention',
                           'messages':[{'role':'user','content':prompt}],
                           'cache_prompt':True,
                           'chat_template_kwargs':{'tesy_template_date':row['template_date']}}))
    return protocol,config,tasks


def physical_budget():
    idle=sum(strict_json(path.read_text())['duration_s'] for path in
             Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed()+idle+8400>16*3600:
        raise GateError('C37 physical budget cannot cover 20 requests and cleanup')


def validate(root,protocol,config,raw):
    samples=[strict_json(line) for line in
             (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    maxima=validate_receipt(protocol,config,raw,samples,root,run_id=RUN_ID,
                            protocol_filename=f'protocols/{RUN_ID}.json',expected_results=20)
    cpu=summarize_samples(samples,require_safe=True)
    normalized=strict_json((root/'raw'/f'{RUN_ID}.normalized.json').read_text())
    gate=validate_c2(normalized,{name:protocol[name] for name in PROTOCOL})
    ids=strict_json((root/'raw'/f'{RUN_ID}.tokenization.json').read_text())
    expected=protocol['expected_request_ids']
    if list(ids)!=expected or [x['id'] for x in raw['results']]!=expected or \
            raw['elapsed_s']<3600:
        raise GateError('C37 request identities/duration incomplete')
    commons=[]
    for i,result in enumerate(raw['results']):
        name=result['id'];usage=result['usage'];stream=result.get('stream_metrics')
        if usage['prompt_tokens']!=len(ids[name]) or \
                not 0<usage['completion_tokens']<=64 or \
                type(stream) is not dict or stream.get('done_observed') is not True or \
                type(stream.get('first_text_chunk_s')) not in (int,float):
            raise GateError('C37 request output/count/fence incomplete')
        if i:
            prior=raw['results'][i-1]
            if result['started_s']-prior['ended_s']<179.5:
                raise GateError('C37 frozen inter-request idle missing')
            common=server.validate_adjacent_cache(ids[expected[i-1]],ids[name],
                                                  result['timings']['cache_n'],1900,32)
            commons.append(common)
        elif result['timings']['cache_n']!=0:
            raise GateError('C37 first request cache unexpectedly warm')
    return maxima,cpu,gate,commons,ids


def run(root,commit):
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):
        raise GateError('C37 measurement commit/worktree not frozen')
    physical_budget()
    protocol,config,tasks=frozen(root)
    path=root/'protocols'/f'{RUN_ID}.json'
    preflight=strict_json((root/'preflight.json').read_text())
    if strict_json(path.read_text())!=protocol or \
            preflight['guard_status']!='READY_FOR_IDLE_ADMISSION' or \
            subprocess.check_output(['powerprofilesctl','get'],text=True).strip()!=preflight['power_profile']:
        raise GateError('C37 preflight/protocol changed')
    scope=check_scope();no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('C37 cooling active before idle')
    idle=thermal_idle(root,RUN_ID,match_tolerance_c=(5,5,3),max_start_c=(50,50,45))
    save_new(root/f'{RUN_ID}-idle.json',idle)
    receipt={'schema':'c37-retention-receipt-v1','run_id':RUN_ID,
             'measurement_commit':commit,'status':'THERMAL_PREFLIGHT_BLOCKED',
             'idle':idle,'completed_requests':0,'default_changed':False}
    if idle['status']!='PASS':
        save_new(root/f'{RUN_ID}-receipt.json',receipt)
        return 2
    if check_scope()!=scope or cpu_capture()['processor_cooling_max_state'] or \
            model_stat()!=protocol['c37']['model_stat']:
        raise GateError('C37 scope/cooling/model changed after idle')
    no_other_model()
    args=SimpleNamespace(model='target120b',suite=config['suite'],run_id=RUN_ID,protocol=path)
    try:
        rc=server.run(args,protocol,config,tasks,MODEL)
        launch_error=None
    except (GateError,OSError,RuntimeError,ValueError) as exc:
        rc=1;launch_error=f'{type(exc).__name__}: {exc}'
    raw_path=root/'raw'/f'{RUN_ID}.json'
    receipt.update(status='FAIL_RESOURCES_OR_EVIDENCE',runner_returncode=rc,
                   launch_error=launch_error,
                   protocol_sha256=sha256(path),
                   raw_sha256=sha256(raw_path) if raw_path.exists() else None)
    if raw_path.exists():
        raw=strict_json(raw_path.read_text())
        receipt.update(returncode=raw['returncode'],stop_reasons=raw['stop_reasons'],
                       elapsed_s=raw['elapsed_s'],completed_requests=len(raw['results']))
        thermal={'CPU_TJMAX_100','CPU_PROCESSOR_COOLING_ACTIVE',
                 'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING','THERMAL_GUARD'}
        if any(reason in thermal for reason in raw['stop_reasons']):
            receipt['status']='FAIL_THERMAL_LIMIT'
        elif rc==0:
            try:
                maxima,cpu,gate,commons,ids=validate(root,protocol,config,raw)
                first=raw['results'][:10];last=raw['results'][10:]
                compact={'first_ten_request_median_s':median(x['ended_s']-x['started_s'] for x in first),
                         'last_ten_request_median_s':median(x['ended_s']-x['started_s'] for x in last),
                         'first_ten_decode_median_tok_s':median(x['timings']['predicted_per_second'] for x in first),
                         'last_ten_decode_median_tok_s':median(x['timings']['predicted_per_second'] for x in last)}
                receipt.update(status='PASS_SPACED_SESSION_RETENTION',maxima=maxima,
                               cpu_diagnostics=cpu,server_gate=gate,
                               adjacent_common_prefix_ids=commons,
                               token_id_sha256={k:digest(v) for k,v in ids.items()},
                               metrics=compact,
                               results=[{'id':x['id'],'usage':x['usage'],'timings':x['timings'],
                                         'request_elapsed_s':x['ended_s']-x['started_s'],
                                         'stream_metrics':x.get('stream_metrics'),
                                         'message_sha256':digest(x['message'])} for x in raw['results']])
            except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
    save_new(root/f'{RUN_ID}-receipt.json',receipt)
    print(json.dumps({'run_id':RUN_ID,'status':receipt['status'],
                      'completed':receipt['completed_requests'],
                      'elapsed_s':receipt.get('elapsed_s'),
                      'reason':receipt.get('reason')},allow_nan=False))
    return 0 if receipt['status']=='PASS_SPACED_SESSION_RETENTION' else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--run',action='store_true')
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    root=args.root
    if root!=ROOT or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C37 output root changed')
    if args.freeze:
        protocol,_,_=frozen(root)
        save_new(root/'protocols'/f'{RUN_ID}.json',protocol)
        print(json.dumps({'status':'FROZEN','protocol_sha256':sha256(root/'protocols'/f'{RUN_ID}.json')}))
        return 0
    if not args.measurement_commit:
        parser.error('--measurement-commit required')
    return run(root,args.measurement_commit)


if __name__=='__main__':
    raise SystemExit(main())
