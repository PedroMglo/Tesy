#!/usr/bin/env python3
"""Freeze and run a bounded C57 layer-0 diagnostic against its own OFF arm."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from host_resource_policy import (GIB, derive_policy, freeze_protocol_resource_limits,
                                  validate_resource_protocol)
from run_bounded import backend_library_hashes, sha256
import c61_boundary_gate as gate

REPO = Path(__file__).resolve().parents[1]
BACKEND = Path('/tmp/tesy-c57-backend-20260928')
MODEL = Path('/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf')
BINARY = REPO/'tools/c60_boundary_capture'
IDS = REPO/'results/c2-target-numeric-v1.ids'
CAP = 18*GIB
ARMS = (('c61-p12-wave-off01',False),('c61-p12-wave-on01',True))


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True).strip()


def write_new(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def model_stat():
    item=MODEL.stat()
    return {'dev':item.st_dev,'ino':item.st_ino,'size':item.st_size,
            'mtime_ns':item.st_mtime_ns}


def frozen(root):
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy:
        raise GateError('fresh inventory/resource derivation changed')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    backend_sha=git('-C',BACKEND,'rev-parse','HEAD')
    if git('-C',BACKEND,'status','--porcelain') or \
       backend_sha!='aac3bbde35575044d290798a120cde038f85b670':
        raise GateError('C57 isolated backend source identity differs')
    stat=model_stat()
    if stat['size']!=63387346208 or any(stat[k]!=snapshot['model_stat'][source]
       for k,source in (('dev','dev'),('ino','inode'),('size','size_bytes'),
                        ('mtime_ns','mtime_ns'))):
        raise GateError('canonical model stat differs from fresh inventory')
    protocol={'schema':'c61-boundary-protocol-v1','campaign_id':root.name,
              'hypothesis':'C57 shared-activation conversion repair removes C48 layer0/prefill0 active mismatch',
              'alternative':'a second producer/consumer/alias/race defect remains',
              'claim':'same-profile bitwise at frozen targeted boundary only; no timing',
              'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
              'model_stat':stat,'backend_sha':backend_sha,
              'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
              'backend_libraries_sha256':backend_library_hashes(str(BINARY),BACKEND),
              'capture_binary_sha256':sha256(BINARY),'capture_source_sha256':sha256(REPO/'tools/c60_boundary_capture.cpp'),
              'runner_sha256':sha256(__file__),'gate_sha256':sha256(gate.__file__),
              'bounded_monitor_sha256':sha256(REPO/'tools/run_bounded.py'),
              'input_sha256':sha256(IDS),'input_case':'log_medium',
              'call_plan':{'prefill_external_calls':1,'prefill_ids':189,'n_batch':256,'n_ubatch':32,
                           'decode_external_calls':32,'teacher_forced':True,
                           'selected_logits':['prefill_final','decode0','decode1','decode7','decode31']},
              'profile':{'ngl':12,'slots':32,'context':4096,'swa_full':True,
                         'flash_attention':True,'kv_dtype':'F16','kv_offload':True,
                         'base_env':{'LLAMA_MOE_STREAM_NO_PRELOAD':'1'}},
              'arms':[{'run_id':name,'skip_parked':on,'order':i+1}
                      for i,(name,on) in enumerate(ARMS)],
              'resources':resources,'limits':{'timeout_s_per_arm':600},
              'stop_rule':'first failed arm or mismatch ends C61; no retry',
              'publication':'local commits only; raw untracked'}
    validate_resource_protocol(protocol)
    return protocol


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new root/raw required')
    protocol=frozen(root)
    write_new(root/'protocol.json',protocol)
    write_new(root/'preflight.json',{'schema':'c61-freeze-v1',
        'utc':datetime.now(timezone.utc).isoformat(),
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'policy_sha256':sha256(root/'resource-policy.json'),
        'status':'FROZEN_NOT_MEASURED','selected_cap_bytes':CAP,
        'backend_sha':protocol['backend_sha'],
        'capture_binary_sha256':protocol['capture_binary_sha256'],
        'model_stat':protocol['model_stat']})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','root':str(root),
                      'resource_cap_max':protocol['resources']['inventory_snapshot']['memory']['MemAvailable_min']}))


def verify_raw(root,run_id,on,protocol):
    stem=root/'raw'/run_id
    manifest=strict_json(Path(str(stem)+'.json').read_text())
    if manifest['run_id']!=run_id or manifest['returncode']!=0 or manifest['stop_reason'] is not None or \
       manifest['backend_sha']!=protocol['backend_sha'] or \
       manifest['binary_sha256']!=protocol['capture_binary_sha256'] or \
       manifest['workload_sha256']!=protocol['input_sha256'] or \
       manifest['resource_authority']!=protocol['resources'] or \
       manifest['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       manifest['backend_libraries_sha256']!=protocol['backend_libraries_sha256'] or \
       manifest['explicit_env']!=({'LLAMA_MOE_STREAM_NO_PRELOAD':'1',
                                    'TESY_CPU_WAVE_SKIP_PARKED':'1'} if on else
                                   {'LLAMA_MOE_STREAM_NO_PRELOAD':'1'}) or \
       not manifest['mapped_libraries_match_ldd'] or \
       manifest['artifact_identity']['stat_at_launch']!=manifest['artifact_identity']['stat_at_end'] or \
       any(manifest['artifact_identity']['stat_at_launch'][key]!=protocol['model_stat'][source]
           for key,source in (('dev','dev'),('inode','ino'),('size_bytes','size'),
                              ('mtime_ns','mtime_ns'))):
        raise GateError('bounded manifest identity/resource/exit failed')
    for suffix,expected in manifest['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=expected:
            raise GateError('bounded raw hash changed: '+suffix)
    capture=Path(str(stem)+'.capture')
    _,_,coverage=gate.validate(capture,on)
    return manifest,coverage


def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):
        raise GateError('measurement commit/tree not clean')
    protocol=strict_json((root/'protocol.json').read_text())
    current=frozen(root)
    if current!=protocol or protocol['runner_sha256']!=sha256(__file__) or \
       sha256(root/'snapshot.json')!=strict_json((root/'preflight.json').read_text())['snapshot_sha256']:
        raise GateError('C61 frozen protocol or identity changed')
    for order,(run_id,on) in enumerate(ARMS,1):
        if model_stat()!=protocol['model_stat'] or \
           sha256(BINARY)!=protocol['capture_binary_sha256'] or \
           backend_library_hashes(str(BINARY),BACKEND)!=protocol['backend_libraries_sha256'] or \
           git('-C',BACKEND,'rev-parse','HEAD')!=protocol['backend_sha']:
            raise GateError('per-arm model/backend/binary/library identity changed')
        no_other_model()
        command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
                 '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
                 '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
                 '--backend','streaming','--backend-root',str(BACKEND),
                 '--output-root',str((root/'raw').resolve()),
                 '--variant','P12-C57-wave-on' if on else 'P12-C57-wave-off',
                 '--workload',str(IDS),
                 '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
                 '--timeout-s','600','--resource-protocol',str(root/'protocol.json'),
                 '--require-telemetry','--ready-marker','C7_CONTEXT_READY',
                 '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1']
        if on:command+=['--env','TESY_CPU_WAVE_SKIP_PARKED=1']
        command+=['--',str(BINARY),str(MODEL),str(IDS),
                  str(root/'raw'/f'{run_id}.capture'),'--ngl','12']
        process=subprocess.run(command,capture_output=True,text=True,check=False)
        receipt={'schema':'c61-arm-receipt-v1','run_id':run_id,'order':order,
                 'skip_parked':on,'measurement_commit':commit,
                 'scope_returncode':process.returncode,
                 'systemd_stderr_tail':process.stderr[-1000:],
                 'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        manifest_path=root/'raw'/f'{run_id}.json'
        if manifest_path.exists():
            manifest=strict_json(manifest_path.read_text())
            receipt.update(raw_manifest_sha256=sha256(manifest_path),
                           returncode=manifest.get('returncode'),
                           stop_reason=manifest.get('stop_reason'),
                           elapsed_s=manifest.get('elapsed_s'),
                           maxima=manifest.get('maxima'))
            if process.returncode==0:
                try:
                    _,coverage=verify_raw(root,run_id,on,protocol)
                    receipt.update(status='PASS_CAPTURE_SCOPE',coverage=coverage)
                except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
                    receipt['reason']=f'{type(exc).__name__}: {exc}'
        else:
            receipt['reason']='bounded manifest absent'
        write_new(root/f'{run_id}-receipt.json',receipt)
        print(json.dumps({'run_id':run_id,'status':receipt['status'],
                          'reason':receipt.get('reason'),'elapsed_s':receipt.get('elapsed_s')}),flush=True)
        if receipt['status']!='PASS_CAPTURE_SCOPE':
            return 1
    result=gate.compare(root/'raw'/f'{ARMS[0][0]}.capture',
                        root/'raw'/f'{ARMS[1][0]}.capture')
    result.update(measurement_commit=commit,
                  run_ids=[name for name,_ in ARMS],
                  raw_manifest_sha256={name:sha256(root/'raw'/f'{name}.json') for name,_ in ARMS})
    write_new(root/'boundary-summary.json',result)
    print(json.dumps({'status':result['status'],'mismatch':result['mismatch']}),flush=True)
    return 0 if result['status']=='SAME_PROFILE_BITWISE_PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('freeze','run'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    if args.mode=='freeze':freeze(args.root.resolve())
    else:
        if not args.measurement_commit:parser.error('--measurement-commit required')
        raise SystemExit(run(args.root.resolve(),args.measurement_commit))
