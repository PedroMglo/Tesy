#!/usr/bin/env python3
"""Prospective C60 callback-continuation repair: one bounded observer OFF arm."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess

from c2_gate import GateError,strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from host_resource_policy import GIB,validate_resource_protocol
from run_bounded import backend_library_hashes,file_identity,relevant_environment,sha256
import c7_boundary_gate as c7
import c61_boundary_gate as c61
import c67_noop_observer_run as old
from c63_numeric_gate import numeric_ids
from c66_wave_id_diagnostic import diagnostic,BACKEND,IDS,REPO

BINARY=REPO/'tools/c68_boundary_capture'
RUN='c68-p12-capture-off01'
CAP=18*GIB

def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True).strip()

def save_new(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')

def frozen(root):
    p=old.frozen(root)
    libs=backend_library_hashes(str(BINARY),BACKEND)
    if libs!=p['backend_libraries_sha256']:
        raise GateError('C68 captured libraries differ from C67 no-op')
    p.update(schema='c68-callback-continuation-repair-v1',
      hypothesis='C60 returned false on delivery of selected out-of-scope attn_post_norm nodes, cancelling graph splits; returning true on delivery removes the C66 invalid ID',
      alternative='a further async copy/alias/backend defect remains after the callback contract repair',
      binary_sha256=sha256(BINARY),
      source_sha256=sha256(REPO/'tools/c68_boundary_capture.cpp'),
      runner_sha256=sha256(__file__),run_id=RUN,
      call_plan={'prefill_external_calls':1,'prompt_ids':189,'teacher_forced_steps':32,
                 'observer':'C60 layer0 capture with selected out-of-scope delivery returning true'},
      claim='one same-profile observer OFF diagnostic; no wave ON/timing promotion')
    validate_resource_protocol(p)
    return p

def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():raise GateError('new root/raw required')
    p=frozen(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c68-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_NOT_MEASURED',
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json')})

def verify(root,p):
    stem=root/'raw'/RUN
    mpath=Path(str(stem)+'.json')
    m=strict_json(mpath.read_text())
    capture=root/'raw'/(RUN+'.capture')
    expected=[str(BINARY),str(MODEL),str(IDS),str(capture),'--ngl','12']
    if m['run_id']!=RUN or m['variant']!='P12-C68-observer-off' or \
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
        raise GateError('C68 provenance/completion changed')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:raise GateError('bounded raw hash changed')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):dev for i,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or any(
       placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C68 placement/direct I/O changed')
    _,logits,coverage=c61.validate(capture,False)
    plain=old.OLD/'raw/c66-p12-plain01'
    control,_=c7.off(plain,numeric_ids(IDS))
    mismatch=[phase for phase in c7.LOGIT_PHASES if logits[phase]!=control[phase]]
    if mismatch:raise GateError('FAIL_SAME_PROFILE_FIDELITY: selected logits differ: '+','.join(mismatch))
    return {'manifest_sha256':sha256(mpath),'coverage':coverage,
            'same_profile_selected5':'BITWISE_EQUAL_C66_PLAIN',
            'maxima':m['maxima'],'elapsed_s':m['elapsed_s']}

def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=p or pre['protocol_sha256']!=sha256(root/'protocol.json') or \
       pre['snapshot_sha256']!=sha256(root/'snapshot.json'):
        raise GateError('frozen C68 identity changed')
    if file_identity(MODEL)!=p['model_stat'] or sha256(BINARY)!=p['binary_sha256']:
        raise GateError('per-arm model/binary changed')
    no_other_model()
    stem=root/'raw'/RUN
    if Path(str(stem)+'.json').exists():raise GateError('no-replace run exists')
    capture=root/'raw'/(RUN+'.capture')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',RUN,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(BACKEND),
             '--output-root',str((root/'raw').resolve()),
             '--variant','P12-C68-observer-off','--workload',str(IDS),
             '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
             '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
             '--require-telemetry','--ready-marker','C68_CONTEXT_READY',
             '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1','--',str(BINARY),str(MODEL),
             str(IDS),str(capture),'--ngl','12']
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c68-run-receipt-v1','run_id':RUN,'measurement_commit':commit,
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
            try:receipt.update(status='PASS_CAPTURE_REPAIR_TESTED_SCOPE',source=verify(root,p))
            except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
                if 'FAIL_SAME_PROFILE_FIDELITY' in receipt['reason']:
                    receipt['status']='FAIL_SAME_PROFILE_FIDELITY'
        elif receipt['invalid_id'] is not None:
            receipt['status']='FAIL_NUMERIC_RUNTIME_ASSERTION'
            receipt['reason']='invalid routed ID after callback repair; no recovery'
        else:receipt['reason']='child/scope failed without targeted diagnostic'
    else:receipt['reason']='bounded manifest absent'
    save_new(root/'raw'/(RUN+'-receipt.json'),receipt)
    save_new(root/'diagnostic-summary.json',receipt)
    print(json.dumps({'run_id':RUN,'status':receipt['status'],
                      'invalid_id':receipt.get('invalid_id'),
                      'reason':receipt.get('reason')}),flush=True)
    return 0 if receipt['status']=='PASS_CAPTURE_REPAIR_TESTED_SCOPE' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path);parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
