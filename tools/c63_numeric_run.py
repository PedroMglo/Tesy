#!/usr/bin/env python3
"""Freeze and run P14 OFF/ON/OFF numeric boundary on unchanged C35 backend."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess

from c2_gate import GateError,strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import original, BACKEND, MODEL
from host_resource_policy import GIB,derive_policy,freeze_protocol_resource_limits,validate_resource_protocol
from run_bounded import backend_library_hashes,file_identity,relevant_environment,sha256
import c63_numeric_gate as gate

REPO=Path(__file__).resolve().parents[1]
IDS=REPO/'results/c2-target-numeric-v1.ids'
LATENCY=REPO/'results/c3-p1-latency-ids01.tsv'
CAP=18*GIB


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True).strip()


def write_new(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def frozen(root):
    _,server_binary,prior_stat=original()
    if git('-C',BACKEND,'rev-parse','HEAD')!='c3759bad92c0e6f71bb936afea9b0a162fb83f76' or \
       git('-C',BACKEND,'status','--porcelain'):
        raise GateError('C35 backend source changed')
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy:
        raise GateError('fresh C63 inventory changed')
    stat=file_identity(MODEL)
    if any(stat[k]!=snapshot['model_stat'][source] for k,source in
           (('dev','dev'),('inode','inode'),('size_bytes','size_bytes'),('mtime_ns','mtime_ns'))) or \
       any(stat[key]!=prior_stat[old] for key,old in
           (('dev','dev'),('inode','ino'),('size_bytes','size'),('mtime_ns','mtime_ns'))):
        raise GateError('verified canonical model changed')
    binaries={name:REPO/'tools'/name for name in
              ('c63_profile_probe','c63_boundary_capture','c63_layer_reference')}
    hashes={name:sha256(path) for name,path in binaries.items()}
    libs=backend_library_hashes(str(binaries['c63_profile_probe']),BACKEND)
    server_libs=backend_library_hashes(str(server_binary),BACKEND)
    if libs!=backend_library_hashes(str(binaries['c63_boundary_capture']),BACKEND) or \
       any(server_libs.get(name)!=digest for name,digest in libs.items()):
        raise GateError('P14 probe/capture session library pin differs')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    protocol={'schema':'c63-p14-numeric-protocol-v1','campaign_id':root.name,
              'objective':'P14 same-profile active routed states, full logits and fresh-process repetition',
              'alternative':'placement or observer changes arithmetic/routing; numerical failure blocks timing',
              'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
              'model_stat':stat,'backend_sha':git('-C',BACKEND,'rev-parse','HEAD'),
              'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
              'backend_libraries_sha256':libs,'binaries_sha256':hashes,
              'sources_sha256':{name:sha256(REPO/'tools'/(name+'.cpp')) for name in binaries},
              'runner_sha256':sha256(__file__),'gate_sha256':sha256(gate.__file__),
              'monitor_sha256':sha256(REPO/'tools/run_bounded.py'),
              'numeric_ids_path':str(IDS),'numeric_ids_sha256':sha256(IDS),
              'latency_tsv_path':str(LATENCY),'latency_tsv_sha256':sha256(LATENCY),
              'profile':{'ngl':14,'first_gpu_layer_expected':23,'output_device_expected':'CUDA0',
                         'slots':32,'context':8192,'batch':256,'ubatch':32,
                         'swa_full':True,'kv_unified':True,'kv_offload':True,
                         'kv_dtype':'F16','preload':'ON','threads':8,
                         'flash_attention':True},
              'call_plan':{'prefill_external_calls':1,'prefill_ids':189,
                           'teacher_forced_decode_steps':32,
                           'selected_logits':list(gate.c7.LOGIT_PHASES),
                           'numeric_states':250,'masked_states':2},
              'arms':[{'run_id':run_id,'variant':variant,'binary':binary,'order':i+1}
                      for i,(run_id,variant,binary) in enumerate(gate.ARMS)],
              'resources':resources,'limits':{'timeout_s_per_arm':600},
              'stop_rule':'first resource, identity, payload, fidelity or reference failure; no retry',
              'publication':'local only; raw untracked'}
    validate_resource_protocol(protocol)
    return protocol


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new C63 root/raw required')
    protocol=frozen(root)
    write_new(root/'protocol.json',protocol)
    write_new(root/'preflight.json',{'schema':'c63-freeze-v1',
        'utc':datetime.now(timezone.utc).isoformat(),
        'status':'FROZEN_NOT_MEASURED',
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'resource_policy_sha256':sha256(root/'resource-policy.json'),
        'protocol_sha256':sha256(root/'protocol.json'),
        'selected_cap_bytes':CAP,'backend_sha':protocol['backend_sha'],
        'model_stat':protocol['model_stat']})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','root':str(root)}))


def validate_arm(root,run_id,variant,binary,protocol):
    return gate.source(root,run_id,variant,binary,protocol)


def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C63 measurement commit/tree or relevant environment changed')
    protocol=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=protocol or sha256(root/'protocol.json')!=pre['protocol_sha256'] or \
       sha256(root/'snapshot.json')!=pre['snapshot_sha256']:
        raise GateError('C63 frozen numeric identity changed')
    receipts=[]
    for order,(run_id,variant,binary) in enumerate(gate.ARMS,1):
        if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or \
           file_identity(MODEL)!=protocol['model_stat'] or \
           sha256(REPO/binary)!=protocol['binaries_sha256'][Path(binary).name]:
            raise GateError('C63 per-arm code/model identity changed')
        no_other_model()
        command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
                 '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
                 '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
                 '--backend','streaming','--backend-root',str(BACKEND),
                 '--output-root',str((root/'raw').resolve()),
                 '--variant',variant,'--workload',str(IDS),
                 '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
                 '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
                 '--require-telemetry','--ready-marker','C63_CONTEXT_READY','--',
                 str((REPO/binary).resolve()),str(MODEL),str(IDS)]
        if binary.endswith('profile_probe'):
            command += [str(LATENCY),str(root/'raw'/run_id),'--ngl','14',
                        '--case','log_medium']
        else:
            command += [str(root/'raw'/(run_id+'.capture')),'--ngl','14']
        process=subprocess.run(command,capture_output=True,text=True,check=False)
        receipt={'schema':'c63-arm-receipt-v1','run_id':run_id,'order':order,
                 'measurement_commit':commit,'scope_returncode':process.returncode,
                 'scope_stderr_tail':process.stderr[-1000:],
                 'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        manifest_path=root/'raw'/f'{run_id}.json'
        if manifest_path.is_file():
            manifest=strict_json(manifest_path.read_text())
            receipt.update(raw_manifest_sha256=sha256(manifest_path),
                           returncode=manifest.get('returncode'),
                           stop_reason=manifest.get('stop_reason'),
                           elapsed_s=manifest.get('elapsed_s'),maxima=manifest.get('maxima'))
            if process.returncode==0:
                try:
                    receipt['source']=validate_arm(root,run_id,variant,binary,protocol)
                    if binary.endswith('profile_probe'):
                        gate.c7.off(root/'raw'/run_id,gate.numeric_ids(IDS))
                    else:
                        gate.c7.capture(root/'raw'/(run_id+'.capture'))
                    receipt['status']='PASS_ARM_SCHEMA'
                except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                    receipt['reason']=f'{type(exc).__name__}: {exc}'
            elif manifest.get('returncode')!=0:
                receipt['reason']='child process failure; inspect stderr assertion/error'
        else:
            receipt['reason']='bounded manifest absent'
        receipts.append(receipt)
        print(json.dumps({'run_id':run_id,'status':receipt['status'],
                          'reason':receipt.get('reason'),'elapsed_s':receipt.get('elapsed_s')}),flush=True)
        if receipt['status']!='PASS_ARM_SCHEMA':break
    for receipt in receipts:
        write_new(root/(receipt['run_id']+'-receipt.json'),receipt)
    if len(receipts)!=3 or any(x['status']!='PASS_ARM_SCHEMA' for x in receipts):
        return 1
    try:
        result=gate.compare(root,protocol)
    except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
        result={'schema':'c63-p14-numeric-gate-v1','status':'FAIL_RESOURCES_OR_EVIDENCE',
                'reason':f'{type(exc).__name__}: {exc}'}
    result.update(measurement_commit=commit,run_ids=[x[0] for x in gate.ARMS])
    write_new(root/'boundary-summary.json',result)
    print(json.dumps({'status':result['status'],'mismatch':result.get('mismatch'),
                      'reason':result.get('reason')}),flush=True)
    return 0 if result['status']=='SAME_PROFILE_LOGITS_AND_CAPTURE_PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('freeze','run'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.mode=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
