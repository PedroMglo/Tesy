#!/usr/bin/env python3
"""Wave-skip ON targeted layer0 boundary against preserved C68 repaired OFF."""
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
import c61_boundary_gate as gate
import c68_capture_repair_run as off
from c66_wave_id_diagnostic import diagnostic,BACKEND,IDS,REPO

RUN='c69-p12-wave-on01'
BINARY=REPO/'tools/c68_boundary_capture'
OLD=REPO/'results/c68-callback-repair-20260928T1636Z'
CAP=18*GIB

def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True).strip()

def save_new(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')

def frozen(root):
    p=off.frozen(root)
    old_manifest=strict_json((OLD/'manifest.json').read_text())
    old_capture=OLD/'raw/c68-p12-capture-off01.capture'
    for name,record in old_manifest['raw_sha256'].items():
        if name.startswith('raw/c68-p12-capture-off01.capture/'):
            path=OLD/name
            if sha256(path)!=record['sha256'] or path.stat().st_size!=record['bytes']:
                raise GateError('C68 OFF capture raw hash changed')
    if gate.validate(old_capture,False)[2]['core_states']!=len(gate.CORE):
        raise GateError('C68 OFF boundary changed')
    p.update(schema='c69-wave-on-targeted-boundary-v1',
       hypothesis='C57 parked-pair CPU MMID skip with shared conversion repaired preserves active layer0 states and five full logits bitwise',
       alternative='a distinct active-pair/arithmetic/alias defect remains after the C68 observer fix',
       runner_sha256=sha256(__file__),run_id=RUN,
       C68_off_manifest_sha256=sha256(OLD/'manifest.json'),
       C68_off_capture_index_sha256=sha256(old_capture/'index.tsv'),
       intervention={'TESY_CPU_WAVE_SKIP_PARKED':'1'},
       claim='targeted P12 layer0/prefill0 same-profile fidelity only; full reference/timing NOT_RUN')
    validate_resource_protocol(p)
    return p

def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():raise GateError('new root/raw required')
    p=frozen(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c69-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_NOT_MEASURED',
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json')})

def verify(root,p):
    stem=root/'raw'/RUN
    mpath=Path(str(stem)+'.json')
    m=strict_json(mpath.read_text())
    capture=root/'raw'/(RUN+'.capture')
    expected=[str(BINARY),str(MODEL),str(IDS),str(capture),'--ngl','12']
    env={'LLAMA_MOE_STREAM_NO_PRELOAD':'1','TESY_CPU_WAVE_SKIP_PARKED':'1'}
    if m['run_id']!=RUN or m['variant']!='P12-C69-wave-on' or \
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
       m['explicit_env']!=env or m['returncode']!=0 or m['stop_reason'] is not None:
        raise GateError('C69 provenance/completion changed')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:raise GateError('bounded raw hash changed')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):dev for i,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or any(
       placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C69 placement/direct I/O changed')
    result=gate.compare(OLD/'raw/c68-p12-capture-off01.capture',capture)
    return {'manifest_sha256':sha256(mpath),'maxima':m['maxima'],
            'elapsed_s':m['elapsed_s'],'boundary':result}

def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=p or pre['protocol_sha256']!=sha256(root/'protocol.json') or \
       pre['snapshot_sha256']!=sha256(root/'snapshot.json') or \
       sha256(OLD/'manifest.json')!=p['C68_off_manifest_sha256']:
        raise GateError('frozen C69 identity changed')
    if file_identity(MODEL)!=p['model_stat'] or sha256(BINARY)!=p['binary_sha256'] or \
       backend_library_hashes(str(BINARY),BACKEND)!=p['backend_libraries_sha256']:
        raise GateError('per-arm model/binary/library changed')
    no_other_model()
    stem=root/'raw'/RUN
    if Path(str(stem)+'.json').exists():raise GateError('no-replace run exists')
    capture=root/'raw'/(RUN+'.capture')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',RUN,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(BACKEND),
             '--output-root',str((root/'raw').resolve()),
             '--variant','P12-C69-wave-on','--workload',str(IDS),
             '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
             '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
             '--require-telemetry','--ready-marker','C68_CONTEXT_READY',
             '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1',
             '--env','TESY_CPU_WAVE_SKIP_PARKED=1','--',str(BINARY),str(MODEL),
             str(IDS),str(capture),'--ngl','12']
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c69-run-receipt-v1','run_id':RUN,'measurement_commit':commit,
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
            try:
                data=verify(root,p)
                receipt['source']=data
                receipt['status']=data['boundary']['status']
            except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
        elif receipt['invalid_id'] is not None:
            receipt['status']='FAIL_NUMERIC_RUNTIME_ASSERTION'
            receipt['reason']='invalid routed ID after observer repair in ON arm'
        else:receipt['reason']='child/scope failed without targeted diagnostic'
    else:receipt['reason']='bounded manifest absent'
    save_new(root/'raw'/(RUN+'-receipt.json'),receipt)
    save_new(root/'boundary-summary.json',receipt)
    print(json.dumps({'run_id':RUN,'status':receipt['status'],
                      'invalid_id':receipt.get('invalid_id'),
                      'mismatch':receipt.get('source',{}).get('boundary',{}).get('mismatch'),
                      'reason':receipt.get('reason')}),flush=True)
    return 0 if receipt['status']=='SAME_PROFILE_BITWISE_PASS' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path);parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
