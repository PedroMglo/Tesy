#!/usr/bin/env python3
"""Bounded C15 original/diagnostic 513-ID bridge with server resource gates."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, MODEL_SHA, configuration, digest, validate_receipt
from run_bounded import backend_library_hashes, relevant_environment, sha256


ROOT = Path('results/c34b-wave-profile-20260928T0054Z')
ORIGINAL = Path('/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming')
DIAGNOSTIC = Path('/tmp/tesy-c15-backend-20260927')
SPECS = (('c34b-control-cold513', ORIGINAL, 'CONTROL', 1),
         ('c34b-c15-plain-cold513', DIAGNOSTIC, 'C15_PLAIN', 2),
         ('c34b-c15-profile-cold513', DIAGNOSTIC, 'C15_PROFILE', 3))
BY_ID = {row[0]: row for row in SPECS}
TOKEN_SHA = 'e19cb14e4c38e8f1b153a58c1d3450ded2b402d82f5798961a1246285099d316'


def save_new(path, row):
    with path.open('x') as out:
        json.dump(row, out, sort_keys=True, indent=2, allow_nan=False)
        out.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def overall(root):
    row = strict_json((root/'protocol.json').read_text())
    if row['schema'] != 'c34b-wave-profile-protocol-v1' or \
            sha256(root/'input.json') != row['input_sha256'] or \
            sha256(root/'usage-contract.json') != row['usage_contract_sha256'] or \
            sha256(Path('results/c33-wave-tracer-feasibility-20260928T0034Z/decision.json')) != row['c33_decision_sha256'] or \
            row['official_prompt_ids_sha256'] != TOKEN_SHA or \
            strict_json(Path('results/c33-wave-tracer-feasibility-20260928T0034Z/decision.json').read_text())['status'] != 'TRACER_BUILD_AND_COLLECTION_PASS_MODEL_FREE' or \
            sha256(Path('results/c34-wave-profile-20260928T0047Z/decision.json')) != row['parent_c34_prelaunch_failure_sha256']:
        raise GateError('C34b frozen inputs/C33 gate changed')
    return row


def frozen(root, spec):
    run_id, backend, phase, order = spec
    high = overall(root)
    if git('-C',str(ORIGINAL),'rev-parse','HEAD') != high['original_backend_commit'] or \
            git('-C',str(DIAGNOSTIC),'rev-parse','HEAD') != high['diagnostic_backend_commit'] or \
            git('-C',str(ORIGINAL),'status','--porcelain') or \
            git('-C',str(DIAGNOSTIC),'status','--porcelain'):
        raise GateError('C34b backend source identity/cleanliness changed')
    protocol, config = configuration(root)
    binary = backend/('build-gcc15/bin/llama-server' if backend == ORIGINAL else
                      'build-c33-nvtx/bin/llama-server')
    if backend == DIAGNOSTIC and sha256(binary) != high['diagnostic_server_sha256']:
        raise GateError('C34b C15 binary changed')
    if phase == 'C15_PROFILE':
        injections = high['profiler_ld_preload'].split(':')
        expected = high['profiler_injection_sha256']
        if len(injections) != 2 or set(Path(path).name for path in injections) != set(expected) or \
                any(sha256(path) != expected[Path(path).name] for path in injections):
            raise GateError('C34b profiler injection identity changed')
        config['explicit_env'] = {'LD_PRELOAD': high['profiler_ld_preload']}
    command=config['server_command']
    command[0]=str(binary)
    command[command.index('-ngl')+1]='12'
    config['backend_root']=str(backend)
    data=strict_json((root/'input.json').read_text())
    source=data['short513']
    task={'id':source['id'],'category':'synthetic-resource',
          'prompt':source['prompt'],'cache_prompt':True}
    tasks=[(task['id'],task)]
    config.update(suite='c34bwave', total_timeout_s=high['server_timeout_s'],
                  request_policy={'mode':'cold513','attempts':1,'max_tokens':4,
                                  'temperature':0,'seed':42,
                                  'per_request_timeout_s':high['server_timeout_s']-20,
                                  'prompt_cache':True},
                  task_ids=[task['id']], n_ctx=8192, pretokenize=True,
                  freeze_token_ids=True, enforce_output_reserve=True,
                  prompt_token_ranges={task['id']:source['expected_prompt_tokens']})
    protocol['identity'].update(backend_sha=git('-C',str(backend),'rev-parse','HEAD'),
                                binary_sha256=sha256(binary),
                                library_sha256=backend_library_hashes(str(binary),backend),
                                config_sha256=digest(config),
                                workload_sha256=sha256(root/'input.json'),
                                input_sha256={'input.json':sha256(root/'input.json'),
                                              'usage-contract.json':sha256(root/'usage-contract.json')})
    if not protocol['identity']['library_sha256']:
        raise GateError('C34b backend libraries unavailable')
    protocol.update(campaign_id='tesy-c34b-wave-profile-20260928',
                    protocol_id=run_id+'-v1', expected_request_ids=[task['id']])
    protocol['limits']['cpu_max_c']=100
    protocol.pop('c9')
    protocol['c18']={'cpu_warning_c':95,'cpu_stop_c':100,
                     'clock_collapse_rule':'five consecutive warning samples below half prewarning median',
                     'explicit_thermal_limit':'any Processor cooling cur_state > 0'}
    protocol['c34b']={'run_id':run_id,'phase':phase,'order':order,
                     'backend_tree':git('-C',str(backend),'rev-parse','HEAD^{tree}'),
                     'backend_dirty':'','model_stat':model_stat(),
                     'runner_sha256':sha256(__file__),
                     'server_runner_sha256':sha256(server.__file__),
                     'monitor_scope':'systemd user scope E18, zero swap',
                     'numerical_scope':'greedy four-token output equality only; full logits NOT_RUN',
                     'timing_promotable':False}
    return protocol,config,tasks


def physical_budget(root):
    idle=sum(strict_json(p.read_text())['duration_s'] for p in
             Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed()+idle+3*(900+300+90)>16*3600:
        raise GateError('C34b physical budget cannot cover frozen three arms')


def run_arm(root, spec, commit):
    run_id, backend, phase, order=spec
    if git('rev-parse','HEAD') != commit or git('status','--porcelain'):
        raise GateError('C34b measurement commit/worktree changed')
    protocol,config,tasks=frozen(root,spec)
    path=root/'protocols'/f'{run_id}.json'
    if strict_json(path.read_text()) != protocol or \
            model_stat() != protocol['c34b']['model_stat'] or \
            protocol['identity']['model_sha256'] != MODEL_SHA:
        raise GateError('C34b frozen protocol/model changed')
    for prior in SPECS[:order-1]:
        r=strict_json((root/f'{prior[0]}-receipt.json').read_text())
        if r['status']!='PASS_DIAGNOSTIC_BRIDGE':
            raise GateError('C34b prior arm did not pass')
    physical_budget(root)
    pre=strict_json((root/'preflight.json').read_text())
    if pre['guard_status'] != 'READY_FOR_IDLE_ADMISSION' or \
            pre['power_source'] != 'AC' or \
            Path('/sys/class/power_supply/AC0/online').read_text().strip() != '1' or \
            subprocess.check_output(['powerprofilesctl','get'],text=True).strip()!=pre['power_profile']:
        raise GateError('C34b physical/power preflight changed')
    if relevant_environment(os.environ) != relevant_environment(config['explicit_env']):
        raise GateError('C34b unfrozen relevant environment')
    scope=check_scope()
    no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('C34b processor cooling active before idle')
    idle=thermal_idle(root,run_id,match_tolerance_c=(5,5,3),max_start_c=(50,50,45))
    save_new(root/f'{run_id}-idle.json',idle)
    receipt={'schema':'c34b-wave-bridge-receipt-v1','run_id':run_id,'phase':phase,
             'order':order,'measurement_commit':commit,'idle':idle,
             'status':'THERMAL_PREFLIGHT_BLOCKED','default_changed':False}
    if idle['status']!='PASS':
        save_new(root/f'{run_id}-receipt.json',receipt)
        return 2
    if order==1:
        save_new(root/'baseline.json',{'cpu_c':idle['end']['cpu_c'],
                 'gpu_c':idle['end']['gpu']['temperature_c'],
                 'nvme_c':idle['end']['nvme_c']})
    if check_scope()!=scope or cpu_capture()['processor_cooling_max_state'] or \
            Path('/sys/class/power_supply/AC0/online').read_text().strip()!='1':
        raise GateError('C34b scope/cooling/power changed after idle')
    no_other_model()
    args=SimpleNamespace(model='target120b',suite=config['suite'],run_id=run_id,protocol=path)
    try:
        rc=server.run(args,protocol,config,tasks,MODEL)
        launch_error=None
    except (GateError,OSError,RuntimeError,ValueError) as exc:
        rc=1;launch_error=f'{type(exc).__name__}: {exc}'
    raw_path=root/'raw'/f'{run_id}.json'
    receipt.update(status='FAIL_RESOURCES_OR_EVIDENCE',runner_returncode=rc,
                   launch_error=launch_error,
                   raw_sha256=sha256(raw_path) if raw_path.exists() else None,
                   protocol_sha256=sha256(path),
                   binary_sha256=protocol['identity']['binary_sha256'])
    if raw_path.exists():
        raw=strict_json(raw_path.read_text())
        receipt.update(returncode=raw['returncode'],stop_reasons=raw['stop_reasons'],
                       server_elapsed_s=raw['elapsed_s'],completed_requests=len(raw['results']))
        samples=[strict_json(line) for line in
                 (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
        thermal={'CPU_TJMAX_100','CPU_PROCESSOR_COOLING_ACTIVE',
                 'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING','THERMAL_GUARD'}
        if any(reason in thermal for reason in raw['stop_reasons']):
            receipt['status']='FAIL_THERMAL_LIMIT'
        elif rc==0:
            try:
                maxima=validate_receipt(protocol,config,raw,samples,root,
                                        run_id=run_id,
                                        protocol_filename='protocols/'+run_id+'.json',
                                        expected_results=1)
                cpu=summarize_samples(samples,require_safe=True)
                normalized=strict_json((root/'raw'/f'{run_id}.normalized.json').read_text())
                gate=validate_c2(normalized,{key:protocol[key] for key in PROTOCOL})
                tokens=strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
                ids=tokens[tasks[0][0]]
                result=raw['results'][0]
                if len(ids)!=513 or digest(ids)!=TOKEN_SHA or \
                        result['usage']['prompt_tokens']!=513 or \
                        result['usage']['completion_tokens']!=4 or \
                        result['timings']['cache_n']!=0 or \
                        result['finish_reason']!='length':
                    raise GateError('C34b frozen 513+4 output/increment invalid')
                if order>1:
                    control=strict_json((root/f'{SPECS[0][0]}-receipt.json').read_text())
                    if result['message']!=control['message'] or \
                            result['finish_reason']!=control['finish_reason']:
                        raise GateError('C34b C15 greedy output differs from original control')
                receipt.update(status='PASS_DIAGNOSTIC_BRIDGE',maxima=maxima,
                               cpu_telemetry=cpu,server_gate=gate,
                               token_ids_sha256=digest(ids),message=result['message'],
                               message_sha256=digest(result['message']),
                               finish_reason=result['finish_reason'],
                               timings=result['timings'],sample_count=len(samples))
            except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
    save_new(root/f'{run_id}-receipt.json',receipt)
    print(json.dumps({'run_id':run_id,'status':receipt['status'],
                      'reason':receipt.get('reason'),
                      'prefill_ms':receipt.get('timings',{}).get('prompt_ms')},allow_nan=False))
    return 0 if receipt['status']=='PASS_DIAGNOSTIC_BRIDGE' else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--freeze',action='store_true')
    group.add_argument('--run',choices=BY_ID)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    root=args.root
    if root!=ROOT or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C34b output root changed')
    if args.freeze:
        hashes={}
        for spec in SPECS:
            protocol,_,_=frozen(root,spec)
            path=root/'protocols'/f'{spec[0]}.json'
            save_new(path,protocol)
            hashes[spec[0]]=sha256(path)
        print(json.dumps({'status':'FROZEN','protocol_sha256':hashes}))
        return
    if not args.measurement_commit:
        parser.error('--measurement-commit required')
    raise SystemExit(run_arm(root,BY_ID[args.run],args.measurement_commit))


if __name__=='__main__':
    main()
