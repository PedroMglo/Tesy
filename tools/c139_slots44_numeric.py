#!/usr/bin/env python3
"""New attempt for frozen uniform44 numeric admission; reuse exact C137 capture build."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

import c137_slots44_numeric as prepared
import c127_slots40_numeric as prior
from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c70_full_boundary_gate import inspect
from c94_session_wave_8k_reference import validate_result, tree_digest
from run_bounded import sha256

REPO=prior.REPO
ROOT_NAME='c139-slots44-numeric-20260929T2315Z'
UNIT='c139'
RUNS={'off':'c139-slots44-off01','on':'c139-slots44-on01'}
CHECKPOINT=REPO/'results/c137-slots44-numeric-20260929T2217Z/epoch-checkpoint.json'
DEADLINE=datetime.fromisoformat('2026-09-30T01:31:15+00:00')
CAP=20*2**30


def budget():
    now=datetime.now(timezone.utc);old=strict_json(CHECKPOINT.read_text())
    physical=old['physical_remaining_lower_bound_s']-60
    wall=(DEADLINE-now).total_seconds()
    if min(wall,physical)<1800+600:raise GateError('C139 envelope/closure not admitted')
    return {'utc':now.isoformat(),'checkpoint_sha256':sha256(CHECKPOINT),
        'physical_remaining_lower_bound_s':physical,'wall_remaining_s':wall,
        'new_inventory_charge_s':60,'numeric_envelope_s':1800,'closure_reserve_s':600}


def expected(root):
    p=prepared.expected(root)
    p.update(schema='c139-uniform44-numeric-v1',campaign_id=ROOT_NAME,
        runner_sha256=sha256(__file__),run_ids=RUNS,
        original_c137_decision_sha256=sha256(REPO/'results/c137-slots44-numeric-20260929T2217Z/decision.json'),
        inherited_runner_sha256=sha256(prepared.__file__),
        limits={'capture_timeout_s':180,'reference_timeout_s_per_layer':30,
                'raw_limit_bytes':512*2**20,'unit_envelope_s':1800,'epoch_deadline_utc':DEADLINE.isoformat()})
    return p


def capture_command(root,p,arm):
    cmd=prepared.capture_command(root,p,arm)
    cmd[cmd.index('--variant')+1]=f'P12-{UNIT.upper()}-slots44-{arm}'
    return cmd


def verify_capture(root,p,arm):
    stem=root/'raw'/RUNS[arm];path=Path(str(stem)+'.json');m=strict_json(path.read_text())
    expected_env={'TESY_CPU_WAVE_SKIP_PARKED':'1'} if arm=='on' else {}
    if m['run_id']!=RUNS[arm] or m['variant']!=f'P12-{UNIT.upper()}-slots44-{arm}' or \
       m['binary_sha256']!=p['binary_sha256'] or m['backend_sha']!=prepared.BACKEND_SHA or \
       m['backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['explicit_env']!=expected_env or m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       m['artifact_identity']['stat_at_end']!=p['model_stat'] or m['workload_sha256']!=p['numeric_ids_sha256'] or \
       m['resource_authority']!=p['resources'] or m['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       m['returncode']!=0 or m['stop_reason'] is not None:
        raise GateError('C139 capture identity/resource/completion failed')
    for suffix,h in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=h:raise GateError('C139 output hash mismatch')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):d for i,d in __import__('re').findall(r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or any(placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or 'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C139 actual placement/direct I/O changed')
    result=inspect(Path(str(stem)+'.capture'),skip_on=arm=='on')
    return {'status':'PASS_CAPTURE_ARM','manifest_sha256':sha256(path),'coverage':result['coverage'],
        'sentinels':result['sentinels'],'elapsed_s':m['elapsed_s'],'maxima':m['maxima']}


def configure(root=None):
    global ROOT_NAME, RUNS, UNIT, CHECKPOINT
    if root is not None:
        ROOT_NAME=root.name
        UNIT=root.name.split('-',1)[0]
        if not __import__('re').fullmatch(r'c[0-9]+',UNIT):raise GateError('new numeric unit ID invalid')
        RUNS={arm:f'{UNIT}-slots44-{arm}01' for arm in ('off','on')}
        if UNIT!='c139':CHECKPOINT=REPO/'results/c139-slots44-numeric-20260929T2315Z/epoch-checkpoint.json'
    prepared.ROOT_NAME=ROOT_NAME;prepared.RUNS=RUNS;prepared.PRIOR=CHECKPOINT
    prepared.configure()
    prior.expected=expected;prior.budget=budget
    prior.capture_command=capture_command;prior.verify_capture=verify_capture


def reference(root,commit):
    p=prior.frozen(root,commit)
    if strict_json((root/'boundary-summary.json').read_text())['status']!='SAME_PROFILE_BITWISE_PASS':
        raise GateError('C139 OFF/ON prerequisite absent')
    capture=root/'raw'/f'{RUNS["on"]}.capture';digest=tree_digest(capture);receipts=[]
    for layer in range(36):
        no_other_model();rid=f'{UNIT}-ref-l{layer:02d}-01';stem=root/'raw'/rid
        cmd=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}','-p','MemorySwapMax=0','--',
            'python3','tools/run_bounded.py','--run-id',rid,'--model-id','gpt-oss-120b-mxfp4-gguf',
            '--backend','streaming','--backend-root',str(prepared.BACKEND),'--output-root',str(root/'raw'),
            '--variant',f'P12-{UNIT.upper()}-slots44-canonical-layer{layer}','--workload',str(capture/'index.tsv'),
            '--cache-condition','resident-canonical-one-layer-page-cache-uncontrolled','--timeout-s','30',
            '--resource-protocol',str(root/'protocol.json'),'--require-telemetry','--',
            p['reference_binary_path'],str(prepared.MODEL),str(capture),str(layer),'--ngl','12']
        proc=subprocess.run(cmd,capture_output=True,text=True,cwd=REPO,check=False)
        row={'run_id':rid,'layer':layer,'measurement_commit':commit,'capture_tree':digest,
            'scope_returncode':proc.returncode,'scope_stderr_tail':proc.stderr[-1200:],'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        try:
            if proc.returncode:raise GateError('C139 reference scope/monitor failed')
            mpath=Path(str(stem)+'.json');m=strict_json(mpath.read_text())
            if m['returncode']!=0 or m['stop_reason'] is not None or m['binary_sha256']!=p['reference_binary_sha256'] or \
               m['backend_sha']!=prepared.BACKEND_SHA or m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
               m['artifact_identity']['stat_at_launch']!=p['model_stat'] or m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
               m['workload_sha256']!=sha256(capture/'index.tsv') or m['resource_authority']!=p['resources']:
                raise GateError('C139 reference identity/resource/completion failed')
            for suffix,h in m['output_sha256'].items():
                if sha256(Path(str(stem)+suffix))!=h:raise GateError('C139 reference hash mismatch')
            value=strict_json(Path(str(stem)+'.stdout').read_text())
            if not validate_result(value,layer):raise GateError('C139 canonical FFN/router mismatch')
            row.update(status='PASS_CANONICAL_LAYER',elapsed_s=m['elapsed_s'],numeric_rows=value['numeric_rows'],
                masked_rows=value['masked_rows'],raw_manifest_sha256=sha256(mpath))
        except Exception as exc:row['reason']=f'{type(exc).__name__}: {exc}'
        prior.save_new(root/f'{rid}-receipt.json',row);receipts.append(row)
        print(json.dumps({'layer':layer,'status':row['status'],'reason':row.get('reason')}),flush=True)
        if row['status']!='PASS_CANONICAL_LAYER':break
    summary={'status':'PASS_FULL_REFERENCE' if len(receipts)==36 and all(x['status']=='PASS_CANONICAL_LAYER' for x in receipts)
        else 'FAIL_SAME_PROFILE_OR_EVIDENCE','layers':[x['layer'] for x in receipts],
        'numeric_rows':sum(x.get('numeric_rows',0) for x in receipts),'masked_rows':sum(x.get('masked_rows',0) for x in receipts),
        'measurement_commit':commit,'capture_tree':digest}
    prior.save_new(root/'reference-summary.json',summary)
    return 0 if summary['status']=='PASS_FULL_REFERENCE' else 1


def run(root,commit):
    start=datetime.now(timezone.utc);mono=time.monotonic();status='FAIL_RESOURCES_OR_EVIDENCE';reason=None;code=1
    try:
        for arm in ('off','on'):
            if prior.capture(root,commit,arm):raise GateError(f'C139 {arm} capture failed')
        if reference(root,commit):raise GateError('C139 reference failed')
        status='PASS_UNIFORM44_NUMERIC_BOUNDARY_AND_36_FFN';code=0
    except Exception as exc:reason=f'{type(exc).__name__}: {exc}'
    elapsed=time.monotonic()-mono
    prior.save_new(root/'unit-receipt.json',{'status':status,'reason':reason,'measurement_commit':commit,
        'started_utc':start.isoformat(),'ended_utc':datetime.now(timezone.utc).isoformat(),'elapsed_s':elapsed,
        'includes':'OFF/ON and references/launch/cleanup; inventory charged separately60s',
        'deadline_utc':DEADLINE.isoformat(),'model_active_s':'see per-process manifests'})
    old=strict_json(CHECKPOINT.read_text());charged=old['physical_charged_upper_estimate_s']+60+elapsed
    prior.save_new(root/'epoch-checkpoint.json',{'epoch_id':old['epoch_id'],'utc':datetime.now(timezone.utc).isoformat(),
        'physical_charged_upper_estimate_s':charged,'physical_remaining_lower_bound_s':28800-charged,
        'wall_remaining_s':(DEADLINE-datetime.now(timezone.utc)).total_seconds(),
        'prior_checkpoint_sha256':sha256(CHECKPOINT),'unit_receipt_sha256':sha256(root/'unit-receipt.json')})
    return code


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('freeze','run'));ap.add_argument('root',type=Path)
    ap.add_argument('--measurement-commit');a=ap.parse_args();root=a.root.resolve();configure(root)
    if a.mode=='freeze':prior.freeze(root)
    elif a.measurement_commit:raise SystemExit(run(root,a.measurement_commit))
    else:ap.error('measurement commit required')
