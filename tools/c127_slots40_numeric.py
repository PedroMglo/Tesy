#!/usr/bin/env python3
"""Frozen slots40 OFF/ON boundary and independent resident FFN reference."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from c66_wave_id_diagnostic import IDS
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
from c70_full_boundary_gate import inspect, compare
from c94_session_wave_8k_reference import validate_result, tree_digest


REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = 'c127-slots40-numeric-20260929T1654Z'
BACKEND = Path('/tmp/tesy-c75-backend-20260928')
BACKEND_SHA = '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5'
CAP = 18 * GIB
RUNS = {'off':'c127-slots40-off01','on':'c127-slots40-on01'}
REFERENCE = Path('/tmp/c77_layer_reference')
EPOCH_START = datetime.fromisoformat('2026-09-29T13:31:15+00:00')


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True,cwd=REPO).strip()


def save_new(path,value):
    with Path(path).open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def budget():
    prior_path=REPO/'results/c126-wave-quality-20260929T1610Z/epoch-checkpoint.json'
    prior=strict_json(prior_path.read_text())
    now=datetime.now(timezone.utc)
    wall=(EPOCH_START+timedelta(hours=12)-now).total_seconds()
    physical=prior['physical_remaining_lower_bound_s']
    reserve=2*600+36*180+600
    if min(wall,physical)<reserve:
        raise GateError('C127 capture/reference worst-case and closure not admitted')
    return {'schema':'c127-budget-admission-v1','utc':now.isoformat(),
            'wall_remaining_s':wall,'physical_remaining_lower_bound_s':physical,
            'worst_case_s':reserve,'prior_checkpoint_sha256':sha256(prior_path)}


def expected(root):
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy or policy['memory']['cap_max_bytes']<CAP:
        raise GateError('C127 live policy does not admit E18')
    stat=file_identity(MODEL)
    if any(stat[k]!=snapshot['model_stat'][k] for k in ('dev','inode','size_bytes','mtime_ns')):
        raise GateError('C127 model stat differs from live snapshot')
    if git('-C',BACKEND,'rev-parse','HEAD')!=BACKEND_SHA or \
       git('-C',BACKEND,'status','--porcelain'):
        raise GateError('C127 C75 backend changed')
    binary=root/'build/c127_slots40_boundary_capture'
    if not binary.is_file() or not REFERENCE.is_file():
        raise GateError('C127 probe or resident reference absent')
    libraries=backend_library_hashes(str(binary),BACKEND)
    ref_libraries=backend_library_hashes(str(REFERENCE),BACKEND)
    if not libraries or libraries!=ref_libraries:
        raise GateError('C127 mapped library set unavailable/inconsistent')
    old=strict_json((REPO/'results/c80-session-numeric-source-20260928T1940Z/protocol.json').read_text())
    profile=dict(old['profile']);profile['slots']=40
    p={'schema':'c127-slots40-numeric-v1','campaign_id':root.name,
       'hypothesis':'40 slots improve residency and wave capacity while preserving exact routed computation',
       'alternative':'additional slots do not help or breach RAM/VRAM; changed wave geometry breaks numeric fidelity',
       'claim':'189+32 P12/8K short boundary and 36 resident FFN layers; full 8K sequence/attention/KV independent NOT_RUN',
       'model_stat':stat,'model_sha256_previously_verified':old['model_sha256_previously_verified'],
       'backend_sha':BACKEND_SHA,'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
       'binary_sha256':sha256(binary),'binary_path':str(binary),
       'backend_libraries_sha256':libraries,
       'reference_binary_sha256':sha256(REFERENCE),
       'reference_binary_path':str(REFERENCE),
       'reference_source_sha256':sha256(REPO/'tools/c7_layer_reference.cpp'),
       'reference_gate_sha256':sha256(REPO/'tools/c94_session_wave_8k_reference.py'),
       'capture_source_sha256':sha256(REPO/'tools/c127_slots40_boundary_capture.cpp'),
       'runner_sha256':sha256(__file__),
       'boundary_gate_sha256':sha256(REPO/'tools/c70_full_boundary_gate.py'),
       'numeric_ids_sha256':sha256(IDS),'profile':profile,'call_plan':old['call_plan'],
       'resources':freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP),
       'limits':{'capture_timeout_s':600,'reference_timeout_s_per_layer':180,
                 'raw_limit_bytes':512*2**20},'run_ids':RUNS,
       'numeric_gate':'OFF/ON bitwise active states and full logits, then 36 resident canonical layers bitwise; any mismatch/stop closes C127',
       'default_changed':False,'publication':'local only'}
    validate_resource_protocol(p)
    return p


def freeze(root):
    if root.name!=ROOT_NAME or not (root/'raw').is_dir() or (root/'protocol.json').exists():
        raise GateError('C127 fresh root/raw required')
    save_new(root/'budget-admission.json',budget())
    p=expected(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c127-freeze-v1','status':'FROZEN_NOT_MEASURED',
        'utc':datetime.now(timezone.utc).isoformat(),
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'policy_sha256':sha256(root/'resource-policy.json')})


def frozen(root,commit):
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('C127 measurement HEAD/worktree/environment not frozen')
    p=expected(root)
    pre=strict_json((root/'preflight.json').read_text())
    if p!=strict_json((root/'protocol.json').read_text()) or \
       pre['protocol_sha256']!=sha256(root/'protocol.json') or \
       pre['snapshot_sha256']!=sha256(root/'snapshot.json') or \
       pre['policy_sha256']!=sha256(root/'resource-policy.json'):
        raise GateError('C127 protocol/inventory changed after freeze')
    return p


def capture_command(root,p,arm):
    run_id=RUNS[arm]
    capture=root/'raw'/(run_id+'.capture')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
        '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
        '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
        '--backend','streaming','--backend-root',str(BACKEND),
        '--output-root',str((root/'raw').resolve()),
        '--variant',f'P12-C127-slots40-{arm}',
        '--workload',str(IDS),
        '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
        '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
        '--require-telemetry','--ready-marker','C80_CONTEXT_READY']
    if arm=='on':command+=['--env','TESY_CPU_WAVE_SKIP_PARKED=1']
    command+=['--',p['binary_path'],str(MODEL),str(IDS),str(capture),'--ngl','12']
    return command


def verify_capture(root,p,arm):
    run_id=RUNS[arm];stem=root/'raw'/run_id
    manifest_path=Path(str(stem)+'.json')
    m=strict_json(manifest_path.read_text())
    expected_env={'TESY_CPU_WAVE_SKIP_PARKED':'1'} if arm=='on' else {}
    if m['run_id']!=run_id or m['variant']!=f'P12-C127-slots40-{arm}' or \
       m['binary_sha256']!=p['binary_sha256'] or \
       m['backend_sha']!=p['backend_sha'] or \
       m['backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['explicit_env']!=expected_env or m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
       m['workload_sha256']!=p['numeric_ids_sha256'] or \
       m['resource_authority']!=p['resources'] or \
       m['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       m['returncode']!=0 or m['stop_reason'] is not None:
        raise GateError('C127 capture provenance/completion invalid')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:
            raise GateError('C127 capture raw SHA mismatch')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):dev for i,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or any(placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C127 placement or direct I/O changed')
    observed=inspect(Path(str(stem)+'.capture'),skip_on=arm=='on')
    return {'status':'PASS_CAPTURE_ARM','manifest_sha256':sha256(manifest_path),
            'coverage':observed['coverage'],'sentinels':observed['sentinels'],
            'elapsed_s':m['elapsed_s'],'maxima':m['maxima']}


def capture(root,commit,arm):
    p=frozen(root,commit)
    if arm=='on':
        previous=strict_json((root/'raw'/f'{RUNS["off"]}-receipt.json').read_text())
        if previous['status']!='PASS_CAPTURE_ARM':
            raise GateError('C127 OFF prerequisite failed')
    no_other_model()
    run_id=RUNS[arm]
    command=capture_command(root,p,arm)
    proc=subprocess.run(command,capture_output=True,text=True,check=False,cwd=REPO)
    receipt={'schema':'c127-capture-receipt-v1','run_id':run_id,
             'measurement_commit':commit,'scope_returncode':proc.returncode,
             'scope_stderr_tail':proc.stderr[-1200:],
             'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    try:
        if proc.returncode!=0:raise GateError('C127 scope/monitor failed')
        receipt.update(verify_capture(root,p,arm))
        if arm=='on':
            left=root/'raw'/(RUNS['off']+'.capture')
            right=root/'raw'/(RUNS['on']+'.capture')
            comparison=compare(left,right)
            save_new(root/'boundary-summary.json',comparison)
            if comparison['status']!='SAME_PROFILE_BITWISE_PASS':
                raise GateError('C127 slots40 OFF/ON active boundary mismatch')
            receipt['status']='PASS_SAME_PROFILE_BOUNDARY'
    except Exception as exc:
        receipt['status']='FAIL_SAME_PROFILE_OR_EVIDENCE' if proc.returncode==0 else 'FAIL_RESOURCES_OR_EVIDENCE'
        receipt['reason']=f'{type(exc).__name__}: {exc}'
    save_new(root/'raw'/f'{run_id}-receipt.json',receipt)
    print(json.dumps({'run_id':run_id,'status':receipt['status'],
                      'reason':receipt.get('reason'),'elapsed_s':receipt.get('elapsed_s')},allow_nan=False),flush=True)
    return 0 if receipt['status'].startswith('PASS_') else 1


def reference(root,commit):
    p=frozen(root,commit)
    on_receipt=strict_json((root/'raw'/f'{RUNS["on"]}-receipt.json').read_text())
    boundary=strict_json((root/'boundary-summary.json').read_text())
    if on_receipt['status']!='PASS_SAME_PROFILE_BOUNDARY' or \
       boundary['status']!='SAME_PROFILE_BITWISE_PASS':
        raise GateError('C127 numeric capture prerequisite absent')
    capture_root=root/'raw'/(RUNS['on']+'.capture')
    capture_tree=tree_digest(capture_root)
    receipts=[]
    for layer in range(36):
        no_other_model()
        run_id=f'c127-ref-l{layer:02d}-01'
        stem=root/'raw'/run_id
        command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
          '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
          '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
          '--backend','streaming','--backend-root',str(BACKEND),
          '--output-root',str((root/'raw').resolve()),
          '--variant',f'P12-C127-slots40-canonical-layer{layer}',
          '--workload',str(capture_root/'index.tsv'),
          '--cache-condition','resident-canonical-one-layer-page-cache-uncontrolled',
          '--timeout-s','180','--resource-protocol',str(root/'protocol.json'),
          '--require-telemetry','--',p['reference_binary_path'],str(MODEL),
          str(capture_root),str(layer),'--ngl','12']
        proc=subprocess.run(command,capture_output=True,text=True,check=False,cwd=REPO)
        receipt={'schema':'c127-reference-receipt-v1','run_id':run_id,'layer':layer,
                 'measurement_commit':commit,'capture_tree':capture_tree,
                 'status':'FAIL_RESOURCES_OR_EVIDENCE','scope_returncode':proc.returncode,
                 'scope_stderr_tail':proc.stderr[-1200:]}
        try:
            if proc.returncode!=0:raise GateError('C127 reference scope/monitor failed')
            mpath=Path(str(stem)+'.json');m=strict_json(mpath.read_text())
            if m['returncode']!=0 or m['stop_reason'] is not None or \
               m['binary_sha256']!=p['reference_binary_sha256'] or \
               m['backend_sha']!=p['backend_sha'] or \
               m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
               m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
               m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
               m['workload_sha256']!=sha256(capture_root/'index.tsv') or \
               m['resource_authority']!=p['resources']:
                raise GateError('C127 reference identity/completion invalid')
            for suffix,digest in m['output_sha256'].items():
                if sha256(Path(str(stem)+suffix))!=digest:
                    raise GateError('C127 reference raw SHA mismatch')
            result=strict_json(Path(str(stem)+'.stdout').read_text())
            if not validate_result(result,layer):
                raise GateError('C127 resident FFN/router mismatch')
            receipt.update(status='PASS_CANONICAL_LAYER',elapsed_s=m['elapsed_s'],
                           raw_manifest_sha256=sha256(mpath),
                           reference_sha256=sha256(Path(str(stem)+'.stdout')),
                           numeric_rows=result['numeric_rows'],masked_rows=result['masked_rows'])
        except Exception as exc:
            receipt['status']='FAIL_SAME_PROFILE_OR_EVIDENCE' if proc.returncode==0 else 'FAIL_RESOURCES_OR_EVIDENCE'
            receipt['reason']=f'{type(exc).__name__}: {exc}'
        save_new(root/f'{run_id}-receipt.json',receipt)
        receipts.append(receipt)
        print(json.dumps({'layer':layer,'status':receipt['status'],
                          'reason':receipt.get('reason')},allow_nan=False),flush=True)
        if receipt['status']!='PASS_CANONICAL_LAYER':break
    status='PASS_FULL_REFERENCE' if len(receipts)==36 and all(x['status']=='PASS_CANONICAL_LAYER' for x in receipts) else 'FAIL_SAME_PROFILE_OR_EVIDENCE'
    save_new(root/'reference-summary.json',{'schema':'c127-reference-summary-v1',
      'status':status,'measurement_commit':commit,'capture_tree':capture_tree,
      'layers':[x['layer'] for x in receipts],
      'numeric_rows':sum(x.get('numeric_rows',0) for x in receipts),
      'masked_rows':sum(x.get('masked_rows',0) for x in receipts)})
    return 0 if status=='PASS_FULL_REFERENCE' else 1


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=('freeze','off','on','reference'))
    ap.add_argument('root',type=Path)
    ap.add_argument('--measurement-commit')
    a=ap.parse_args();root=a.root.resolve()
    if a.mode=='freeze':freeze(root);return
    if not a.measurement_commit:ap.error('measurement commit required')
    if a.mode in RUNS:raise SystemExit(capture(root,a.measurement_commit,a.mode))
    raise SystemExit(reference(root,a.measurement_commit))


if __name__=='__main__':
    main()
