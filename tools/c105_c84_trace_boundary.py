#!/usr/bin/env python3
"""One bounded C84 trace capture compared with C93 same-profile ON bytes."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
import c70_full_boundary_gate as gate
from c84_trace_validate import validate as validate_trace
from c66_wave_id_diagnostic import IDS, REPO

BACKEND=Path('/tmp/tesy-c84-backend-20260928')
BACKEND_SHA='5a1f4c5d9ed06021d58813ffb41792e83f337513'
BINARY=Path('/tmp/c105_session_boundary_capture')
C93=REPO/'results/c93-session-wave-8k-boundary-20260928T2049Z'
C93_ON=C93/'raw/c93-p12-session-wave-on01.capture'
RUN_ID='c105-c84-trace-on01'
CAP=18*GIB


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True).strip()


def save_new(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')


def frozen(root):
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    prior=strict_json((C93/'raw/c93-p12-session-wave-on01-receipt.json').read_text())
    prior_manifest=C93/'raw/c93-p12-session-wave-on01.json'
    if derive_policy(snapshot=snapshot)!=policy or policy['memory']['cap_max_bytes']<CAP or \
       git('-C',BACKEND,'rev-parse','HEAD')!=BACKEND_SHA or \
       git('-C',BACKEND,'status','--porcelain') or \
       prior.get('status')!='SAME_PROFILE_BITWISE_PASS' or \
       prior.get('raw_manifest_sha256')!=sha256(prior_manifest):
        raise GateError('C105 fresh resource/source or C93 prior reference invalid')
    prior_output=strict_json(prior_manifest.read_text())['output_sha256']
    for suffix,digest in prior_output.items():
        if sha256(C93/'raw'/f'c93-p12-session-wave-on01{suffix}')!=digest:
            raise GateError('C105 C93 reference raw hash mismatch')
    stat=file_identity(MODEL)
    if any(stat[key]!=snapshot['model_stat'][key] for key in
           ('dev','inode','size_bytes','mtime_ns')) or not BINARY.is_file():
        raise GateError('C105 model/probe identity changed')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    value={'schema':'c105-c84-8k-boundary-v1','campaign_id':root.name,
           'status':'FROZEN_BEFORE_MODEL',
           'objective':'compare C84 traced 8K P12 189+32 active states and full logits to validated C93 C75 ON; collect bounded continuous expert demand trace',
           'alternative':'instrumentation changes numeric output, overflows, or cannot delimit event semantics',
           'claim_limit':'diagnostic instrumented trace; no production timing/physical NVMe/L2 saving claim',
           'backend_sha':BACKEND_SHA,
           'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
           'binary_sha256':sha256(BINARY),
           'backend_libraries_sha256':backend_library_hashes(str(BINARY),BACKEND),
           'capture_source_sha256':sha256(REPO/'tools/c80_session_boundary_capture.cpp'),
           'runner_sha256':sha256(__file__),
           'trace_validator_sha256':sha256(REPO/'tools/c84_trace_validate.py'),
           'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
           'model_stat':stat,'numeric_ids_sha256':sha256(IDS),
           'C93_on_manifest_sha256':sha256(prior_manifest),
           'C93_on_receipt_sha256':sha256(C93/'raw/c93-p12-session-wave-on01-receipt.json'),
           'profile':strict_json((C93/'protocol.json').read_text())['profile'],
           'call_plan':strict_json((C93/'protocol.json').read_text())['call_plan'],
           'resources':resources,'limits':{'timeout_s':600},'run_id':RUN_ID,
           'trace_path':str((root/'raw'/f'{RUN_ID}.expert.trace').resolve()),
           'stop_rule':'first guard/overflow/nonfinite/mismatch closes unit; no retry',
           'default_changed':False}
    validate_resource_protocol(value)
    return value


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():raise GateError('C105 new root/raw required')
    p=frozen(root);save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c105-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_NOT_MEASURED',
        'protocol_sha256':sha256(root/'protocol.json'),
        'snapshot_sha256':sha256(root/'snapshot.json')})


def verify(root,p):
    stem=root/'raw'/RUN_ID
    mpath=Path(str(stem)+'.json');m=strict_json(mpath.read_text())
    capture=Path(str(stem)+'.capture')
    trace=Path(p['trace_path'])
    expected=[str(BINARY),str(MODEL),str(IDS),str(capture),'--ngl','12']
    env={'TESY_CPU_WAVE_SKIP_PARKED':'1','TESY_C84_EXPERT_TRACE_FILE':str(trace)}
    if m['run_id']!=RUN_ID or m['command']!=expected or \
       m['binary_sha256']!=p['binary_sha256'] or m['backend_sha']!=BACKEND_SHA or \
       m['backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       not m['mapped_libraries_match_ldd'] or m['explicit_env']!=env or \
       m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
       m['workload_sha256']!=p['numeric_ids_sha256'] or \
       m['resource_authority']!=p['resources'] or m['returncode']!=0 or \
       m['stop_reason'] is not None:
        raise GateError('C105 identity/completion invalid')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:raise GateError('C105 raw hash changed')
    observed=gate.inspect(capture,skip_on=True)
    reference=gate.inspect(C93_ON,skip_on=True)
    if observed['core'].keys()!=reference['core'].keys() or \
       observed['logits'].keys()!=reference['logits'].keys() or \
       observed['masks'].keys()!=reference['masks'].keys() or \
       any(observed[key]!=reference[key] for key in ('core','logits','masks')):
        raise GateError('C105 same-profile C84/C75 active state/logit mismatch')
    trace_summary=validate_trace(trace)
    return {'status':'PASS_SAME_PROFILE_C84_TRACE_BOUNDARY',
            'coverage':observed['coverage'],'sentinels':observed['sentinels'],
            'byte_witness_rows':observed['byte_witness_rows'],
            'trace':trace_summary,'trace_sha256':sha256(trace),
            'C93_reference_capture':str(C93_ON),'C93_reference_manifest_sha256':p['C93_on_manifest_sha256']}


def run(root,commit):
    os.chdir(REPO)
    if type(commit) is not str or len(commit)!=40 or \
       git('rev-parse','HEAD')!=commit or git('status','--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C105 full measurement commit/worktree/environment invalid')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if p!=frozen(root) or pre['protocol_sha256']!=sha256(root/'protocol.json') or \
       pre['snapshot_sha256']!=sha256(root/'snapshot.json'):
        raise GateError('C105 frozen protocol changed')
    available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                       if line.startswith('MemAvailable:')))*1024
    if available<CAP+p['resources']['memory']['reserve_bytes']:
        raise GateError('C105 E18 host reserve not admitted')
    no_other_model()
    stem=root/'raw'/RUN_ID;capture=Path(str(stem)+'.capture');trace=Path(p['trace_path'])
    if Path(str(stem)+'.json').exists() or capture.exists() or trace.exists():
        raise GateError('C105 no-replace raw path exists')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',RUN_ID,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(BACKEND),
             '--output-root',str((root/'raw').resolve()),
             '--variant','P12-C105-C84-traced-ON','--workload',str(IDS),
             '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
             '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
             '--require-telemetry','--ready-marker','C80_CONTEXT_READY',
             '--env','TESY_CPU_WAVE_SKIP_PARKED=1',
             '--env',f'TESY_C84_EXPERT_TRACE_FILE={trace}',
             '--',str(BINARY),str(MODEL),str(IDS),str(capture),'--ngl','12']
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c105-run-receipt-v1','run_id':RUN_ID,'measurement_commit':commit,
             'scope_returncode':proc.returncode,'scope_stderr_tail':proc.stderr[-1000:],
             'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    mpath=Path(str(stem)+'.json')
    if mpath.is_file():
        m=strict_json(mpath.read_text());receipt.update(returncode=m.get('returncode'),
            stop_reason=m.get('stop_reason'),maxima=m.get('maxima'),
            elapsed_s=m.get('elapsed_s'),raw_manifest_sha256=sha256(mpath))
        if proc.returncode==0:
            try:
                receipt['comparison']=verify(root,p)
                receipt['status']='PASS_SAME_PROFILE_C84_TRACE_BOUNDARY'
            except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
                if 'same-profile C84/C75 active state/logit mismatch' in str(exc):
                    receipt['status']='FAIL_SAME_PROFILE_FIDELITY'
        else:receipt['reason']='child/scope failed or resource stop'
    else:receipt['reason']='bounded manifest absent'
    save_new(root/'raw'/f'{RUN_ID}-receipt.json',receipt)
    print(json.dumps({'run_id':RUN_ID,'status':receipt['status'],
                      'reason':receipt.get('reason')},allow_nan=False),flush=True)
    return 0 if receipt['status']=='PASS_SAME_PROFILE_C84_TRACE_BOUNDARY' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path);parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs full measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
