#!/usr/bin/env python3
"""Fresh P8/P12 functional arms after the C38 CPU clock telemetry failure."""

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
from c38_quality_grade import grade, self_test
import c38_quality_run as base
from c8_observer_runner import program_physical_consumed
from c9_server_admission import digest, git, validate_receipt
from run_bounded import sha256, gpu_state, mem_available, thermal_state


ROOT=Path('results/c39-quality-recovery-20260928T0438Z')
ARMS=('p8','p12')
PARENT=Path('results/c38-quality12-20260928T0353Z/decision.json')
STOCK=Path('results/c38-quality12-20260928T0353Z/c38-stock20-receipt.json')


def save_new(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def specs(root,arm):
    if arm not in ARMS:
        raise GateError('C39 unknown arm')
    protocol,config,tasks,model=base.get_specs(root,arm)
    config['suite']='c39quality'
    protocol['identity']['config_sha256']=digest(config)
    protocol['c39']=protocol.pop('c38')
    protocol['c39'].update(parent_c38_decision_sha256=sha256(PARENT),
                           reused_stock20_receipt_sha256=sha256(STOCK),
                           runner_sha256=sha256(__file__),
                           claim='fresh 12-task P8/P12 only; C38 stock20B reused with old monitor provenance')
    protocol['c18']['cpu_telemetry_sha256']=sha256('tools/c18_cpu_telemetry.py')
    protocol['identity']['input_sha256'].update({'c38_decision.json':sha256(PARENT),
                                                 'c38_stock20_receipt.json':sha256(STOCK)})
    protocol.update(campaign_id='tesy-c39-quality-recovery-20260928',
                    protocol_id='c39-'+arm+'-v1')
    return protocol,config,tasks,model


def frozen(root,arm):
    high=strict_json((root/'protocol.json').read_text())
    if high['schema']!='c39-quality-recovery-protocol-v1' or \
       high['run_order']!=list(ARMS) or \
       high['parent_c38_decision_sha256']!=sha256(PARENT) or \
       high['reused_stock20_receipt_sha256']!=sha256(STOCK) or \
       high['runner_sha256']!=sha256(__file__) or \
       high['cpu_telemetry_sha256']!=sha256('tools/c18_cpu_telemetry.py') or \
       high['workload_sha256']!=sha256('workloads/c38_quality12.json') or \
       high['grader_sha256']!=sha256('tools/c38_quality_grade.py'):
        raise GateError('C39 source/protocol changed')
    protocol,config,tasks,model=specs(root,arm)
    if strict_json((root/'protocols'/f'c39-{arm}.json').read_text())!=protocol or \
       base.stat(model)!=protocol['c39']['model_stat']:
        raise GateError('C39 arm/model differs from freeze')
    return protocol,config,tasks,model


def budget(arm):
    idle=sum(strict_json(p.read_text())['duration_s'] for p in
             Path('results').glob('c*-*/**/*-idle.json'))
    reserve=(len(ARMS)-ARMS.index(arm))*(6000+900)+300
    if program_physical_consumed()+idle+reserve>16*3600:
        raise GateError('C39 remaining physical budget reserve unavailable')


def run(root,arm,commit):
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):
        raise GateError('C39 measurement commit/worktree not frozen')
    budget(arm);protocol,config,tasks,model=frozen(root,arm)
    pre=strict_json((root/'preflight.json').read_text())
    if pre['status']!='READY' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip()!=pre['power_profile']:
        raise GateError('C39 preflight/power profile changed')
    check_scope();no_other_model()
    if cpu_capture()['processor_cooling_max_state']:
        raise GateError('C39 processor cooling active before idle')
    run_id='c39-'+arm
    idle=thermal_idle(root,run_id,match_tolerance_c=(5,5,3),max_start_c=(50,50,45))
    save_new(root/f'{run_id}-idle.json',idle)
    receipt={'schema':'c39-quality-receipt-v1','run_id':run_id,'arm':arm,
             'measurement_commit':commit,'idle':idle,
             'status':'THERMAL_PREFLIGHT_BLOCKED','completed_requests':0,
             'default_changed':False,'parent_c38_decision_sha256':sha256(PARENT)}
    if idle['status']!='PASS':
        save_new(root/f'{run_id}-receipt.json',receipt)
        return 2
    check_scope();no_other_model()
    args=SimpleNamespace(model='target120b',suite='c39quality',run_id=run_id,
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
                                        expected_results=12)
                cpu=summarize_samples(samples,require_safe=True)
                normalized=strict_json((root/'raw'/f'{run_id}.normalized.json').read_text())
                gate=validate_c2(normalized,{name:protocol[name] for name in PROTOCOL})
                results=[]
                for item in raw['results']:
                    detail=grade(item['id'],item['message'].get('content'))
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
                    raise GateError('C39 validator isolation unavailable')
                receipt.update(status='PASS_COMPLETE_12_TASKS',maxima=maxima,
                               cpu_diagnostics=cpu,server_gate=gate,
                               results=results,pass_count=sum(x['status']=='PASS' for x in results))
            except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
    save_new(root/f'{run_id}-receipt.json',receipt)
    print(json.dumps({'run_id':run_id,'status':receipt['status'],
                      'completed':receipt['completed_requests'],
                      'pass_count':receipt.get('pass_count'),'reason':receipt.get('reason')},allow_nan=False))
    return 0 if receipt['status']=='PASS_COMPLETE_12_TASKS' else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--run',choices=ARMS)
    p.add_argument('--measurement-commit')
    a=p.parse_args();root=a.root
    if root!=ROOT or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C39 output root differs from new identity')
    if a.freeze:
        self_test()
        if strict_json((root/'protocol.json').read_text())['schema']!='c39-quality-recovery-protocol-v1':
            raise GateError('C39 overall schema')
        for arm in ARMS:
            protocol,_,_,_=specs(root,arm)
            save_new(root/'protocols'/f'c39-{arm}.json',protocol)
        print(json.dumps({'status':'FROZEN','arms':list(ARMS)}))
        return 0
    if a.preflight:
        self_test();no_other_model()
        if mem_available()<6*2**30 or not gpu_state() or not thermal_state() or \
           cpu_capture()['processor_cooling_max_state']:
            raise GateError('C39 host resource/thermal preflight failed')
        row={'schema':'c39-preflight-v1','status':'READY',
             'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'power_profile':subprocess.check_output(['powerprofilesctl','get'],text=True).strip(),
             'gpu':gpu_state(),'thermal':thermal_state(),
             'mem_available_bytes':mem_available(),
             'model_stat':base.stat(base.TARGET_MODEL),
             'backend_commit':git('-C',str(base.TARGET_BACKEND),'rev-parse','HEAD'),
             'parent_c38_decision_sha256':sha256(PARENT),
             'reused_stock20_receipt_sha256':sha256(STOCK),
             'validator_self_test':self_test()}
        save_new(root/'preflight.json',row)
        print(json.dumps({'status':'READY','gpu':row['gpu'],'thermal':row['thermal']}))
        return 0
    if not a.measurement_commit:p.error('--measurement-commit required')
    return run(root,a.run,a.measurement_commit)


if __name__=='__main__':
    raise SystemExit(main())
