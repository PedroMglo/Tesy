#!/usr/bin/env python3
"""One bounded C66-backend no-op observer contrast with C66 plain output."""
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
from c63_numeric_gate import numeric_ids
import c7_boundary_gate as c7
from c66_wave_id_diagnostic import diagnostic, BACKEND, IDS, LATENCY, REPO

BINARY=REPO/'tools/c67_noop_observer_probe'
OLD=REPO/'results/c66-wave-id-diagnostic-20260928T1620Z'
RUN='c67-p12-noop-observer01'
CAP=18*GIB

def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True).strip()

def save_new(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')

def frozen(root):
    _,_,prior=original()
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy:raise GateError('resource snapshot changed')
    if git('-C',BACKEND,'rev-parse','HEAD')!='1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22' or \
       git('-C',BACKEND,'status','--porcelain'):
        raise GateError('diagnostic backend changed')
    stat=file_identity(MODEL)
    if any(stat[k]!=prior[old] for k,old in
           (('dev','dev'),('inode','ino'),('size_bytes','size'),('mtime_ns','mtime_ns'))) or \
       any(stat[k]!=snapshot['model_stat'][k] for k in
           ('dev','inode','size_bytes','mtime_ns')):
        raise GateError('model stat changed')
    old_manifest=strict_json((OLD/'manifest.json').read_text())
    plain=OLD/'raw/c66-p12-plain01.f32'
    record=old_manifest['raw_sha256'][str(plain.relative_to(OLD))]
    if sha256(plain)!=record['sha256'] or plain.stat().st_size!=record['bytes']:
        raise GateError('C66 plain output changed')
    libs=backend_library_hashes(str(BINARY),BACKEND)
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    out={'schema':'c67-noop-observer-protocol-v1','campaign_id':root.name,
         'hypothesis':'registering a callback without tensor reads is insufficient to trigger the C66 layer25 invalid ID',
         'alternative':'callback registration itself changes scheduler behavior or exposes the invalid ID',
         'backend_sha':git('-C',BACKEND,'rev-parse','HEAD'),
         'backend_libraries_sha256':libs,'binary_sha256':sha256(BINARY),
         'source_sha256':sha256(REPO/'tools/c67_noop_observer_probe.cpp'),
         'control_source_sha256':sha256(REPO/'tools/c7_profile_probe.cpp'),
         'runner_sha256':sha256(__file__),'monitor_sha256':sha256(REPO/'tools/run_bounded.py'),
         'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
         'model_stat':stat,'numeric_ids_sha256':sha256(IDS),
         'latency_tsv_sha256':sha256(LATENCY),
         'C66_plain_f32_sha256':record['sha256'],
         'C66_plain_manifest_sha256':old_manifest['raw_sha256']['raw/c66-p12-plain01.json']['sha256'],
         'profile':{'ngl':12,'n_ctx':4096,'n_batch':256,'n_ubatch':32,'slots':32,
                    'preload':'OFF','swa_full':True,'kv_unified':False,
                    'kv_type':'F16','threads':8,'io_threads':4},
         'call_plan':{'prefill_external_calls':1,'prompt_ids':189,'teacher_forced_steps':32,
                      'observer':'always false; no tensor read'},
         'resources':resources,'limits':{'timeout_s':600},
         'run_id':RUN,'stop_rule':'first error/guard/mismatch stops; no retry',
         'claim':'diagnostic contrast only; C48/C61/C66 unchanged; no timing',
         'publication':'local only; raw untracked'}
    validate_resource_protocol(out)
    return out

def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():raise GateError('new root/raw required')
    p=frozen(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c67-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_NOT_MEASURED',
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json')})

def verify(root,p):
    stem=root/'raw'/RUN
    mpath=Path(str(stem)+'.json')
    m=strict_json(mpath.read_text())
    expected=[str(BINARY),str(MODEL),str(IDS),str(LATENCY),str(stem),
              '--ngl','12','--case','log_medium']
    if m['run_id']!=RUN or m['variant']!='P12-C67-noop-observer' or \
       m['command']!=expected or m['binary_sha256']!=p['binary_sha256'] or \
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
        raise GateError('C67 provenance/completion changed')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:raise GateError('bounded raw hash changed')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):device for i,device in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or any(
       placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C67 placement/direct I/O changed')
    c7.off(stem,numeric_ids(IDS))
    current=sha256(Path(str(stem)+'.f32'))
    if current!=p['C66_plain_f32_sha256']:
        raise GateError('FAIL_SAME_PROFILE_FIDELITY: no-op observer full33 logits differ from C66 plain')
    return {'manifest_sha256':sha256(mpath),'f32_sha256':current,
            'maxima':m['maxima'],'elapsed_s':m['elapsed_s']}

def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=p or pre['protocol_sha256']!=sha256(root/'protocol.json') or \
       pre['snapshot_sha256']!=sha256(root/'snapshot.json'):
        raise GateError('frozen C67 identity changed')
    if file_identity(MODEL)!=p['model_stat'] or sha256(BINARY)!=p['binary_sha256']:
        raise GateError('per-arm model/binary changed')
    no_other_model()
    stem=root/'raw'/RUN
    if Path(str(stem)+'.json').exists():raise GateError('no-replace run exists')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',RUN,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(BACKEND),
             '--output-root',str((root/'raw').resolve()),
             '--variant','P12-C67-noop-observer','--workload',str(IDS),
             '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
             '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
             '--require-telemetry','--ready-marker','C67_CONTEXT_READY',
             '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1','--',str(BINARY),str(MODEL),
             str(IDS),str(LATENCY),str(stem),'--ngl','12','--case','log_medium']
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c67-run-receipt-v1','run_id':RUN,'measurement_commit':commit,
             'scope_returncode':proc.returncode,'scope_stderr_tail':proc.stderr[-1000:],
             'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    mpath=Path(str(stem)+'.json')
    if mpath.is_file():
        m=strict_json(mpath.read_text())
        receipt.update(returncode=m.get('returncode'),stop_reason=m.get('stop_reason'),
                       maxima=m.get('maxima'),elapsed_s=m.get('elapsed_s'),
                       raw_manifest_sha256=sha256(mpath))
        stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
        receipt['invalid_id']=diagnostic(stderr)
        if proc.returncode==0:
            try:receipt.update(status='PASS_NOOP_OBSERVER_BITWISE',source=verify(root,p))
            except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
                if 'FAIL_SAME_PROFILE_FIDELITY' in receipt['reason']:
                    receipt['status']='FAIL_SAME_PROFILE_FIDELITY'
        elif receipt['invalid_id'] is not None:
            receipt['status']='FAIL_NUMERIC_RUNTIME_ASSERTION'
            receipt['reason']='invalid routed ID with no-op observer; no recovery'
        else:receipt['reason']='child/scope failed without targeted diagnostic'
    else:receipt['reason']='bounded manifest absent'
    save_new(root/'raw'/(RUN+'-receipt.json'),receipt)
    save_new(root/'diagnostic-summary.json',receipt)
    print(json.dumps({'run_id':RUN,'status':receipt['status'],
                      'invalid_id':receipt.get('invalid_id'),
                      'reason':receipt.get('reason')}),flush=True)
    return 0 if receipt['status']=='PASS_NOOP_OBSERVER_BITWISE' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path);parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
