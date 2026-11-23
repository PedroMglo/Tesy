#!/usr/bin/env python3
"""Prospective E18/8K functional comparison of P8, P12, and local 20B."""

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c38_quality_grade import grade, self_test, workload
from c8_observer_runner import program_physical_consumed
from c9_server_admission import configuration as c9_config, digest, git, validate_receipt
from run_bounded import backend_library_hashes, sha256, gpu_state, mem_available, thermal_state


ROOT=Path('results/c38-quality12-20260928T0353Z')
TARGET_BACKEND=Path('/tmp/tesy-c35-backend-20260928')
STOCK_BACKEND=Path('/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/stock')
TARGET_MODEL=Path('/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf')
STOCK_MODEL=Path('/home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf')
MODEL_SHA={'target120b':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
           'stock20b':'52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4'}
ARMS={'stock20-init':('stock20b',13,True), 'stock20-smoke':('stock20b',13,False),
      'stock20':('stock20b',13,False),
      'p8':('target120b',8,False), 'p12':('target120b',12,False)}
RUN_ORDER=('stock20-init','stock20-smoke','stock20','p8','p12')


def save_new(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def stat(path):
    s=path.stat()
    return {'dev':s.st_dev,'inode':s.st_ino,'size_bytes':s.st_size,
            'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


def get_specs(root,arm):
    model_name,ngl,init=ARMS[arm]
    backend=STOCK_BACKEND if model_name=='stock20b' else TARGET_BACKEND
    model=STOCK_MODEL if model_name=='stock20b' else TARGET_MODEL
    binary=backend/'build-gcc15/bin/llama-server' if model_name=='stock20b' else \
           backend/'build-c35-gcc15/bin/llama-server'
    if git('-C',str(backend),'status','--porcelain') or not binary.is_file() or not model.is_file():
        raise GateError('C38 backend dirty or binary/model missing')
    if model_name=='target120b':
        protocol,config=c9_config(root)
        command=config['server_command']
        command[0]=str(binary)
        command[command.index('-ngl')+1]=str(ngl)
    else:
        command=[str(binary),'-m',str(model),'--host','127.0.0.1','--port','18367',
                 '-ngl',str(ngl),'-c','8192','-np','1','-b','256','-ub','32',
                 '-t','8','-tb','8','--no-warmup','--no-cache-prompt','-lv','3',
                 '--load-mode','dio','--lazy-mode','off','--reasoning-effort','medium']
        protocol,config=c9_config(root)
        config['server_command']=command
    smoke=arm=='stock20-smoke'
    names=[] if init else ['c38-capacity-smoke'] if smoke else [x['id'] for x in workload()['tasks']]
    config.update(server_command=command,backend_root=str(backend),
                  output_root=str((root/'raw').resolve()),
                  suite='c38qualityinit' if init else 'c38capacity' if smoke else 'c38quality',
                  task_ids=names,n_ctx=8192,pretokenize=not init,freeze_token_ids=not init,
                  enforce_output_reserve=not init,allow_cache_prompt=False,
                  stream_requests=not init,total_timeout_s=180 if init else 300 if smoke else 6000,
                  request_policy={'mode':'init-only' if init else 'capacity-smoke' if smoke else 'functional-quality',
                                  'attempts':1,'max_tokens':64 if smoke else 3072,'temperature':0,
                                  'seed':42,'reasoning_effort':'medium',
                                  'per_request_timeout_s':180 if smoke else 600})
    libraries=backend_library_hashes(str(binary),backend)
    if not libraries:
        raise GateError('C38 backend libraries unavailable')
    identity={'model_id':model_name,'model_sha256':MODEL_SHA[model_name],
              'backend_sha':git('-C',str(backend),'rev-parse','HEAD'),
              'binary_sha256':sha256(binary),'library_sha256':libraries,
              'config_sha256':digest(config),'workload_sha256':sha256('workloads/c38_quality12.json'),
              'input_sha256':{'workloads/c38_quality12.json':sha256('workloads/c38_quality12.json'),
                              'usage-contract.json':sha256(root/'usage-contract.json'),
                              'protocol.json':sha256(root/'protocol.json')}}
    protocol['identity']=identity
    protocol.update(campaign_id='tesy-c38-functional-20260928',
                    protocol_id='c38-'+arm+'-v1',expected_request_ids=names)
    protocol['limits'].update(memory_max_bytes=int(16.5*2**30),rss_max_bytes=16*2**30,
                              gpu_max_mib=6500,cpu_max_c=100)
    protocol['c38']=protocol.pop('c9')
    protocol['c38'].update(arm=arm,n_gpu_layers=ngl,model_stat=stat(model),
                           backend_tree=git('-C',str(backend),'rev-parse','HEAD^{tree}'),
                           runner_sha256=sha256(__file__),grader_sha256=sha256('tools/c38_quality_grade.py'),
                           workload_sha256=sha256('workloads/c38_quality12.json'),
                           model_free_validator_status='PASS_12_GOLD_AND_12_MUTANT')
    protocol['c18']={'thermal_monitor':'CPU95 warning, CPU100/explicit cooling/clock collapse stop',
                     'monitor_sha256':sha256(server.__file__)}
    tasks=[] if init else [('c38-capacity-smoke',{'id':'c38-capacity-smoke',
             'category':'capacity-smoke','prompt':'Reply exactly OK.',
             'cache_prompt':False})] if smoke else [(x['id'],dict(x,cache_prompt=False,
                       **({'chat_template_kwargs':{'tesy_template_date':'2026-09-28',
                                                  'reasoning_effort':'medium'}}
                          if model_name=='target120b' else {}))) for x in workload()['tasks']]
    return protocol,config,tasks,model


def frozen(root,arm):
    high=strict_json((root/'protocol.json').read_text())
    if high['schema']!='c38-quality12-protocol-v1' or high['run_order']!=list(RUN_ORDER) or \
       high['workload_sha256']!=sha256('workloads/c38_quality12.json') or \
       high['usage_contract_sha256']!=sha256(root/'usage-contract.json') or \
       high['validator_sha256']!=sha256('tools/c38_quality_grade.py') or \
       high['runner_sha256']!=sha256(__file__):
        raise GateError('C38 overall source/protocol changed')
    protocol,config,tasks,model=get_specs(root,arm)
    if strict_json((root/'protocols'/f'c38-{arm}.json').read_text())!=protocol:
        raise GateError('C38 arm profile differs from freeze')
    if stat(model)!=protocol['c38']['model_stat']:
        raise GateError('C38 model identity changed')
    return protocol,config,tasks,model


def budget(arm):
    idle=sum(strict_json(p.read_text())['duration_s'] for p in
             Path('results').glob('c*-*/**/*-idle.json'))
    pending=RUN_ORDER[RUN_ORDER.index(arm):]
    reserve=sum((180 if ARMS[name][2] else 300 if name=='stock20-smoke' else 6000)+900
                for name in pending)+300
    if program_physical_consumed()+idle+reserve>16*3600:
        raise GateError('C38 remaining sequence budget reserve unavailable')


def run(root,arm,measurement_commit):
    if git('rev-parse','HEAD')!=measurement_commit or git('status','--porcelain'):
        raise GateError('C38 measurement commit/worktree not frozen')
    budget(arm);protocol,config,tasks,model=frozen(root,arm)
    if arm=='stock20':
        for prior,want in (('stock20-init','PASS_INIT_ONLY'),
                           ('stock20-smoke','PASS_CAPACITY_SMOKE')):
            if strict_json((root/f'c38-{prior}-receipt.json').read_text())['status']!=want:
                raise GateError('C38 stock20 capacity predecessor absent')
    if strict_json((root/'preflight.json').read_text())['status']!='READY' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip()!= \
       strict_json((root/'preflight.json').read_text())['power_profile']:
        raise GateError('C38 preflight/power profile changed')
    check_scope();no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('C38 processor cooling active before idle')
    run_id='c38-'+arm
    idle=thermal_idle(root,run_id,match_tolerance_c=(5,5,3),max_start_c=(50,50,45))
    save_new(root/f'{run_id}-idle.json',idle)
    receipt={'schema':'c38-quality-receipt-v1','run_id':run_id,'arm':arm,
             'measurement_commit':measurement_commit,'idle':idle,
             'status':'THERMAL_PREFLIGHT_BLOCKED','completed_requests':0,
             'default_changed':False}
    if idle['status']!='PASS':
        save_new(root/f'{run_id}-receipt.json',receipt)
        return 2
    check_scope();no_other_model()
    args=SimpleNamespace(model=ARMS[arm][0],suite=config['suite'],run_id=run_id,
                         protocol=root/'protocols'/f'{run_id}.json')
    try:
        rc=server.run(args,protocol,config,tasks,model)
        launch_error=None
    except (GateError,OSError,RuntimeError,ValueError) as exc:
        rc=1;launch_error=f'{type(exc).__name__}: {exc}'
    raw_path=root/'raw'/f'{run_id}.json'
    receipt.update(status='FAIL_RESOURCES_OR_EVIDENCE',runner_returncode=rc,
                   launch_error=launch_error,raw_sha256=sha256(raw_path) if raw_path.exists() else None)
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
                samples=[strict_json(line) for line in
                         (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
                maxima=validate_receipt(protocol,config,raw,samples,root,
                                        run_id=run_id,protocol_filename=f'protocols/{run_id}.json',
                                        expected_results=len(tasks))
                cpu=summarize_samples(samples,require_safe=True)
                normalized=strict_json((root/'raw'/f'{run_id}.normalized.json').read_text())
                gate=validate_c2(normalized,{name:protocol[name] for name in PROTOCOL}) if tasks else None
                results=[]
                for item in raw['results']:
                    detail=({'status':'PASS'} if arm=='stock20-smoke' else
                            grade(item['id'],item['message'].get('content')))
                    status='FAIL_TRUNCATED' if item['finish_reason']!='stop' else detail['status']
                    results.append({'id':item['id'],'category':item['category'],
                                    'status':status,'detail':detail,
                                    'finish_reason':item['finish_reason'],
                                    'prompt_tokens':item['usage']['prompt_tokens'],
                                    'completion_tokens':item['usage']['completion_tokens'],
                                    'wall_s':item['ended_s']-item['started_s'],
                                    'first_final_content_s':item.get('stream_metrics',{}).get('first_final_content_chunk_s'),
                                    'message_sha256':digest(item['message'])})
                if any(x['status']=='VALIDATOR_ENV_ERROR' for x in results):
                    raise GateError('C38 validator isolation unavailable')
                receipt.update(status='PASS_INIT_ONLY' if not tasks else
                               'PASS_CAPACITY_SMOKE' if arm=='stock20-smoke' else
                               'PASS_COMPLETE_12_TASKS',
                               maxima=maxima,cpu_diagnostics=cpu,server_gate=gate,
                               results=results,pass_count=sum(x['status']=='PASS' for x in results))
            except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
    save_new(root/f'{run_id}-receipt.json',receipt)
    print(json.dumps({'run_id':run_id,'status':receipt['status'],
                      'completed':receipt['completed_requests'],'pass_count':receipt.get('pass_count'),
                      'reason':receipt.get('reason')},allow_nan=False))
    return 0 if receipt['status'] in ('PASS_INIT_ONLY','PASS_CAPACITY_SMOKE',
                                    'PASS_COMPLETE_12_TASKS') else 1


def main():
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--run',choices=ARMS)
    p.add_argument('--measurement-commit')
    a=p.parse_args();root=a.root
    if root!=ROOT or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C38 output root differs from new identity')
    if a.freeze:
        self_test()
        high=strict_json((root/'protocol.json').read_text())
        if high['schema']!='c38-quality12-protocol-v1': raise GateError('C38 overall schema')
        for arm in RUN_ORDER:
            protocol,_,_,_=get_specs(root,arm)
            save_new(root/'protocols'/f'c38-{arm}.json',protocol)
        print(json.dumps({'status':'FROZEN','arms':list(RUN_ORDER)}))
        return 0
    if a.preflight:
        self_test();no_other_model()
        if mem_available()<6*2**30 or not gpu_state() or not thermal_state() or \
           cpu_capture()['processor_cooling_max_state']:
            raise GateError('C38 host resource/thermal preflight failed')
        row={'schema':'c38-preflight-v1','status':'READY',
             'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'power_profile':subprocess.check_output(['powerprofilesctl','get'],text=True).strip(),
             'gpu':gpu_state(),'thermal':thermal_state(),
             'mem_available_bytes':mem_available(),
             'model_stats':{'target120b':stat(TARGET_MODEL),'stock20b':stat(STOCK_MODEL)},
             'backend_commits':{'target':git('-C',str(TARGET_BACKEND),'rev-parse','HEAD'),
                                'stock':git('-C',str(STOCK_BACKEND),'rev-parse','HEAD')},
             'validator_self_test':self_test()}
        save_new(root/'preflight.json',row)
        print(json.dumps({'status':'READY','gpu':row['gpu'],'thermal':row['thermal']}))
        return 0
    if not a.measurement_commit:
        p.error('--measurement-commit required')
    return run(root,a.run,a.measurement_commit)


if __name__=='__main__':
    raise SystemExit(main())
