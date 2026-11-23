#!/usr/bin/env python3
"""Bounded diagnostic of C61 invalid IDs: plain graph, then observer OFF."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess

from c2_gate import GateError,strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import original,MODEL
from host_resource_policy import GIB,derive_policy,freeze_protocol_resource_limits,validate_resource_protocol
from run_bounded import backend_library_hashes,file_identity,relevant_environment,sha256
import c7_boundary_gate as c7
import c61_boundary_gate as c61
from c63_numeric_gate import numeric_ids

REPO=Path(__file__).resolve().parents[1]
BACKEND=Path('/tmp/tesy-c66-wave-id-backend-20260928')
IDS=REPO/'results/c2-target-numeric-v1.ids'
LATENCY=REPO/'results/c3-p1-latency-ids01.tsv'
CAP=18*GIB
ARMS=(('c66-p12-plain01','plain','c66_plain_probe'),
      ('c66-p12-capture01','capture','c66_boundary_capture'))

def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True).strip()

def save_new(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')

def frozen(root):
    _,_,prior=original()
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy:raise GateError('resource snapshot changed')
    if git('-C',BACKEND,'rev-parse','HEAD')!='1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22' or \
       git('-C',BACKEND,'status','--porcelain'):
        raise GateError('diagnostic backend source changed')
    stat=file_identity(MODEL)
    if any(stat[k]!=prior[old] for k,old in
           (('dev','dev'),('inode','ino'),('size_bytes','size'),('mtime_ns','mtime_ns'))) or \
       any(stat[k]!=snapshot['model_stat'][k] for k in
           ('dev','inode','size_bytes','mtime_ns')):
        raise GateError('canonical model changed')
    binaries={name:REPO/'tools'/name for _,_,name in ARMS}
    hashes={name:sha256(path) for name,path in binaries.items()}
    libs=backend_library_hashes(str(binaries['c66_plain_probe']),BACKEND)
    if libs!=backend_library_hashes(str(binaries['c66_boundary_capture']),BACKEND):
        raise GateError('diagnostic arm library hashes differ')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    out={'schema':'c66-invalid-id-diagnostic-v1','campaign_id':root.name,
         'objective':'locate C61 invalid routed ID without altering weights, routing or recovery path',
         'alternatives':['invalid selected ID already reaches plain graph',
                         'observer/capture schedule required to trigger invalid ID',
                         'C61 defect does not reproduce in this run'],
         'backend_sha':git('-C',BACKEND,'rev-parse','HEAD'),
         'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
         'backend_libraries_sha256':libs,'binaries_sha256':hashes,
         'source_sha256':{name:sha256(REPO/'tools'/(source+'.cpp')) for name,source in
                          (('c66_plain_probe','c7_profile_probe'),
                           ('c66_boundary_capture','c60_boundary_capture'))},
         'diagnostic_header_sha256':sha256(BACKEND/'src/llama-moe-stream-id-check.h'),
         'runner_sha256':sha256(__file__),'monitor_sha256':sha256(REPO/'tools/run_bounded.py'),
         'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
         'model_stat':stat,'numeric_ids_sha256':sha256(IDS),
         'latency_tsv_sha256':sha256(LATENCY),
         'profile':{'ngl':12,'n_ctx':4096,'n_batch':256,'n_ubatch':32,'slots':32,
                    'moe_stream':True,'preload':'OFF','swa_full':True,
                    'kv_dtype':'F16','kv_offload':True,'kv_unified':False,
                    'threads':8,'io_threads':4,'direct_io':True},
         'call_plan':{'prefill_external_calls':1,'prefill_ids':189,
                      'teacher_forced_steps':32},
         'arms':[{'run_id':rid,'kind':kind,'binary':name,'order':i+1}
                 for i,(rid,kind,name) in enumerate(ARMS)],
         'resources':resources,'limits':{'timeout_s_per_arm':600},
         'stop_rule':'first nonzero, resource, evidence or same-profile mismatch; no retry',
         'claim':'diagnostic location only; C48/C61 unchanged; no timing promotion',
         'publication':'local only; raw untracked'}
    validate_resource_protocol(out)
    return out

def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():raise GateError('new root/raw required')
    p=frozen(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c66-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_NOT_MEASURED',
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'resource_policy_sha256':sha256(root/'resource-policy.json')})

def diagnostic(stderr):
    match=re.search(r'MoE wave routed-ID diagnostic: layer=(\d+) wave=(\d+) index=(\d+) '
                    r'id=(-?\d+) n_expert=(\d+) n=(\d+) ne0=(\d+) ne1=(\d+)',stderr)
    return dict(zip(('layer','wave','index','id','n_expert','n','ne0','ne1'),
                    map(int,match.groups()))) if match else None

def source(root,arm,p):
    stem=root/'raw'/arm['run_id']
    mpath=Path(str(stem)+'.json')
    m=strict_json(mpath.read_text())
    binary=REPO/'tools'/arm['binary']
    command=[str(binary),str(MODEL),str(IDS)]
    if arm['kind']=='plain':
        command += [str(LATENCY),str(stem),'--ngl','12','--case','log_medium']
    else:command += [str(root/'raw'/(arm['run_id']+'.capture')),'--ngl','12']
    if m['run_id']!=arm['run_id'] or m['variant']!='P12-C66-'+arm['kind'] or \
       m['command']!=command or \
       m['binary_sha256']!=p['binaries_sha256'][arm['binary']] or \
       m['backend_sha']!=p['backend_sha'] or \
       m['backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       not m['mapped_libraries_match_ldd'] or \
       m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
       m['workload_sha256']!=p['numeric_ids_sha256'] or \
       m['resource_authority']!=p['resources'] or \
       m['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       m['explicit_env']!={'LLAMA_MOE_STREAM_NO_PRELOAD':'1'} or \
       m['returncode']!=0 or m['stop_reason'] is not None:
        raise GateError('run identity/completion differs from freeze')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:
            raise GateError('bounded raw hash changed')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(layer):dev for layer,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or any(
       placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('diagnostic placement changed')
    if arm['kind']=='plain':
        selected,seal=c7.off(stem,numeric_ids(IDS))
        return {'manifest_sha256':sha256(mpath),'selected_logits':selected,
                'output_sha256':seal,'maxima':m['maxima']}
    logits,coverage=c61.validate(root/'raw'/(arm['run_id']+'.capture'),False)[1:]
    return {'manifest_sha256':sha256(mpath),'selected_logits':logits,
            'coverage':coverage,'maxima':m['maxima']}

def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=p or pre['protocol_sha256']!=sha256(root/'protocol.json') or \
       pre['snapshot_sha256']!=sha256(root/'snapshot.json'):
        raise GateError('frozen diagnostic identity changed')
    results=[];selected=[]
    for arm in p['arms']:
        if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or \
           file_identity(MODEL)!=p['model_stat'] or \
           sha256(REPO/'tools'/arm['binary'])!=p['binaries_sha256'][arm['binary']]:
            raise GateError('per-arm code/model/binary changed')
        no_other_model()
        rid=arm['run_id'];stem=root/'raw'/rid
        if Path(str(stem)+'.json').exists():raise GateError('no-replace run exists')
        binary=REPO/'tools'/arm['binary']
        command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
                 '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
                 '--run-id',rid,'--model-id','gpt-oss-120b-mxfp4-gguf',
                 '--backend','streaming','--backend-root',str(BACKEND),
                 '--output-root',str((root/'raw').resolve()),
                 '--variant','P12-C66-'+arm['kind'],'--workload',str(IDS),
                 '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
                 '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
                 '--require-telemetry','--ready-marker','C7_CONTEXT_READY',
                 '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1','--',str(binary),str(MODEL),str(IDS)]
        if arm['kind']=='plain':
            command += [str(LATENCY),str(stem),'--ngl','12','--case','log_medium']
        else:command += [str(root/'raw'/(rid+'.capture')),'--ngl','12']
        proc=subprocess.run(command,capture_output=True,text=True,check=False)
        receipt={'schema':'c66-arm-receipt-v1','run_id':rid,'kind':arm['kind'],
                 'measurement_commit':commit,'scope_returncode':proc.returncode,
                 'scope_stderr_tail':proc.stderr[-1000:],'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        mpath=Path(str(stem)+'.json')
        if mpath.is_file():
            m=strict_json(mpath.read_text())
            receipt.update(returncode=m.get('returncode'),stop_reason=m.get('stop_reason'),
                           maxima=m.get('maxima'),elapsed_s=m.get('elapsed_s'),
                           raw_manifest_sha256=sha256(mpath))
            stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
            receipt['invalid_id']=diagnostic(stderr)
            if proc.returncode==0:
                try:
                    data=source(root,arm,p)
                    selected.append(data.pop('selected_logits'))
                    receipt.update(status='PASS_DIAGNOSTIC_ARM',source=data)
                except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                    receipt['reason']=f'{type(exc).__name__}: {exc}'
            elif receipt['invalid_id'] is not None:
                receipt['status']='FAIL_NUMERIC_RUNTIME_ASSERTION'
                receipt['reason']='routed ID outside authoritative expert range; no recovery'
            else:receipt['reason']='child/scope failed without targeted ID diagnostic'
        else:receipt['reason']='bounded manifest absent'
        results.append(receipt)
        save_new(root/'raw'/(rid+'-receipt.json'),receipt)
        print(json.dumps({'run_id':rid,'status':receipt['status'],
                          'invalid_id':receipt.get('invalid_id'),
                          'reason':receipt.get('reason')}),flush=True)
        if receipt['status']!='PASS_DIAGNOSTIC_ARM':break
    if len(results)==2 and all(x['status']=='PASS_DIAGNOSTIC_ARM' for x in results):
        mismatch=[phase for phase in c7.LOGIT_PHASES if selected[0][phase]!=selected[1][phase]]
        status='PASS_DIAGNOSTIC_SCOPE' if not mismatch else 'FAIL_SAME_PROFILE_FIDELITY'
    else:
        mismatch=[];status=results[-1]['status'] if results else 'INCOMPLETE_EVIDENCE'
    summary={'schema':'c66-diagnostic-summary-v1','status':status,
             'measurement_commit':commit,'arms':results,'logit_mismatch_phases':mismatch,
             'C48':'FAIL_SAME_PROFILE_FIDELITY_UNCHANGED',
             'C61':'FAIL_NUMERIC_RUNTIME_ASSERTION_UNCHANGED',
             'timing':'NOT_RUN'}
    save_new(root/'diagnostic-summary.json',summary)
    return 0 if status=='PASS_DIAGNOSTIC_SCOPE' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path);parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
