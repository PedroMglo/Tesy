#!/usr/bin/env python3
"""Three new P12 wave OFF/ON pairs per frozen C73 workload."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from statistics import median
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from run_bounded import file_identity, relevant_environment, sha256
import c73_wave_timing_run as base

REPO = Path(__file__).resolve().parents[1]
ARMS = tuple((case,pair,wave)
    for case in ('cold513','warm154')
    for pair,order in ((1,('off','on')),(2,('on','off')),(3,('off','on')))
    for wave in order)


def run_id(case,pair,wave):
    return f'c74-{case}-p{pair}-wave-{wave}'


def frozen(root):
    p=base.protocol(root)
    prior=REPO/'results/c73-wave-timing-20260928T1713Z/decision.json'
    d=strict_json(prior.read_text())
    if d['status']!='SCREEN_GO_CONFIRMATION_PENDING_BOTH':
        raise GateError('C73 screen prerequisite changed')
    # The exact C73 input is checked by base.protocol against C52b raw and NUMERIC.
    p.update(schema='c74-p12-wave-confirmation-v1',
        hypothesis='C73 large full-model prefill gains persist in three new pairs per case',
        alternative='screen gain depends on order, thermal state or uncontrolled cache',
        runner_sha256=sha256(__file__),C73_decision_sha256=sha256(prior),
        C73_input_sha256=sha256(REPO/'results/c73-wave-timing-20260928T1713Z/input.tsv'),
        arms=[{'run_id':run_id(case,pair,wave),'case':case,'pair':pair,
               'wave':wave,'order':i+1} for i,(case,pair,wave) in enumerate(ARMS)],
        decision={'confirmation':{'new_pairs_per_case':3,
            'median_work_gain_min_percent':8,'all_three_positive':True,
            'median_prefill_gain_min_percent':-5,
            'median_decode_gain_min_percent':-5}},
        causal_start={'mode':'operational warm, alternated order',
            'initial_temperature_reporting':'first monitor sample for each run',
            'pair_match_diagnostic_c':{'cpu':3,'gpu':3,'nvme':2},
            'rule':'unmatched pair limits causal claim; no selective retry'},
        claim_limit='same C73 teacher-forced P12 numeric profile; not exact-prefix server or quality')
    if p['input_tsv_sha256']!=p['C73_input_sha256']:
        raise GateError('C74 input differs from C73 screen')
    return p


def save_new(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new root/raw required')
    p=frozen(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c74-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),
        'status':'FROZEN_NOT_MEASURED',
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json')})


def first_temperatures(root,run):
    path=root/'raw'/(run+'.samples.jsonl')
    with path.open() as f: first=strict_json(f.readline())
    thermal=first['thermal']
    nvme=thermal['nvme_composite_by_sensor']
    return {'cpu_c':thermal['cpu_tctl_c'],'gpu_c':first['gpu']['temperature_c'],
            'nvme_c':max(nvme.values())}


def paired(root,receipts):
    by_id={r['run_id']:r for r in receipts}
    report={'schema':'c74-wave-confirmation-v1','cases':{}}
    for case in ('cold513','warm154'):
        entries=[]
        for pair in (1,2,3):
            a,b=(by_id[run_id(case,pair,wave)] for wave in ('off','on'))
            paths=[root/'raw'/(run_id(case,pair,wave)+'.f32') for wave in ('off','on')]
            if sha256(paths[0])!=sha256(paths[1]):
                raise GateError(f'FAIL_SAME_PROFILE_FIDELITY {case} pair {pair}')
            left,right=a['source']['timing_s'],b['source']['timing_s']
            gains={k:100*(left[k]-right[k])/left[k]
                   for k in ('work','prefill','decode32')}
            temps={wave:first_temperatures(root,run_id(case,pair,wave))
                   for wave in ('off','on')}
            matched=all(abs(temps['off'][k]-temps['on'][k])<=limit
                for k,limit in (('cpu_c',3),('gpu_c',3),('nvme_c',2)))
            entries.append({'pair':pair,'OFF_s':left,'ON_s':right,
                            'gain_percent':gains,'start_c':temps,
                            'start_match_diagnostic':matched})
        for wave in ('off','on'):
            hashes=[sha256(root/'raw'/(run_id(case,i,wave)+'.f32')) for i in (1,2,3)]
            if len(set(hashes))!=1:
                raise GateError(f'FAIL_SAME_PROFILE_FIDELITY {case} wave {wave} fresh repeats')
        med={k:median(x['gain_percent'][k] for x in entries)
             for k in ('work','prefill','decode32')}
        passed=med['work']>=8 and all(x['gain_percent']['work']>0 for x in entries) and \
               med['prefill']>=-5 and med['decode32']>=-5
        report['cases'][case]={'status':'CONFIRMED_TESTED_SCOPE' if passed else 'NO_GO_CONFIRM',
            'median_pair_gain_percent':med,'pairs':entries,
            'all_starts_matched':all(x['start_match_diagnostic'] for x in entries)}
    return report


def run(root,commit):
    os.chdir(REPO)
    if base.git('rev-parse','HEAD')!=commit or base.git('status','--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C74 measurement tree/environment changed')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=p or sha256(root/'protocol.json')!=pre['protocol_sha256'] or \
       sha256(root/'snapshot.json')!=pre['snapshot_sha256']:
        raise GateError('C74 freeze differs')
    receipts=[]
    for arm in p['arms']:
        if base.git('rev-parse','HEAD')!=commit or base.git('status','--porcelain') or \
           file_identity(MODEL)!=p['model_stat'] or sha256(base.BINARY)!=p['binary_sha256']:
            raise GateError('C74 per-arm identity changed')
        no_other_model()
        name=arm['run_id'];stem=root/'raw'/name
        if any(Path(str(stem)+s).exists() for s in ('.json','.f32','.ops.tsv')):
            raise GateError('C74 no-replace arm exists')
        timeout=p['limits']['timeout_cold513_s' if arm['case']=='cold513' else 'timeout_warm154_s']
        cmd=['systemd-run','--user','--scope','-p',f'MemoryMax={base.CAP}',
            '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
            '--run-id',name,'--model-id','gpt-oss-120b-mxfp4-gguf',
            '--backend','streaming','--backend-root',str(base.BACKEND),
            '--output-root',str((root/'raw').resolve()),
            '--variant',f'P12-wave-{arm["wave"]}-timing',
            '--workload',str(root/'input.tsv'),
            '--cache-condition',p['cache_condition'],
            '--timeout-s',str(timeout),'--resource-protocol',str(root/'protocol.json'),
            '--require-telemetry','--ready-marker','C73_CONTEXT_READY',
            '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1']
        if arm['wave']=='on':cmd+=['--env','TESY_CPU_WAVE_SKIP_PARKED=1']
        cmd+=['--',str(base.BINARY),str(MODEL),str(root/'input.tsv'),str(stem),
              '--ngl','12','--case',arm['case']]
        proc=subprocess.run(cmd,capture_output=True,text=True,check=False)
        receipt={'schema':'c74-arm-receipt-v1','run_id':name,
                 'measurement_commit':commit,'scope_returncode':proc.returncode,
                 'scope_stderr_tail':proc.stderr[-1000:],
                 'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        mpath=Path(str(stem)+'.json')
        if mpath.is_file():
            m=strict_json(mpath.read_text())
            receipt.update(returncode=m.get('returncode'),stop_reason=m.get('stop_reason'),
                           elapsed_s=m.get('elapsed_s'),maxima=m.get('maxima'))
            if proc.returncode==0:
                try:
                    receipt['source']=base.arm_source(root,arm,p)
                    receipt['start_c']=first_temperatures(root,name)
                    receipt['status']='PASS_ARM'
                except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                    receipt['reason']=f'{type(exc).__name__}: {exc}'
            else:receipt['reason']='scope/child nonzero; inspect bounded stderr'
        else:receipt['reason']='bounded manifest absent'
        receipts.append(receipt)
        save_new(root/'raw'/(name+'-receipt.json'),receipt)
        print(json.dumps({'run_id':name,'status':receipt['status'],
                          'timing':receipt.get('source',{}).get('timing_s'),
                          'start_c':receipt.get('start_c'),
                          'reason':receipt.get('reason')}),flush=True)
        if receipt['status']!='PASS_ARM':break
    with (root/'runs.jsonl').open('x') as out:
        for row in receipts:out.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
    if len(receipts)==len(ARMS):
        try:report=paired(root,receipts)
        except (GateError,ValueError,TypeError,OSError) as exc:
            report={'schema':'c74-wave-confirmation-v1',
                    'status':'FAIL_SAME_PROFILE_FIDELITY','reason':str(exc)}
    else:
        report={'schema':'c74-wave-confirmation-v1',
                'status':'FAIL_RESOURCES_OR_EVIDENCE','reason':'arm failed; stopped'}
    save_new(root/'timing-pairs.json',report)
    return 0 if 'cases' in report else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run requires measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
