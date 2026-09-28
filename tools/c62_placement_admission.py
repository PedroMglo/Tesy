#!/usr/bin/env python3
"""P14/slots32 E18 session backend admission: init, then one bounded forward."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from c2_gate import GateError,strict_json
import c2_server_run as server
from c9_server_admission import validate_receipt
from c17_thermal_recovery import no_other_model
from c58_resource_canary import original, BACKEND, MODEL
from host_resource_policy import GIB,derive_policy,freeze_protocol_resource_limits,validate_resource_protocol
from run_bounded import sha256,backend_library_hashes

REPO=Path(__file__).resolve().parents[1]
INPUT=REPO/'results/c17-thermal-recovery-20260927T1656Z/input.json'
ACCOUNT=REPO/'results/c59-placement-static-20260928T1453Z/accounting.json'
CAP=18*GIB
ARMS=(('init','c62-p14-init01'),('forward','c62-p14-cold51301'))


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True).strip()


def write_new(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')


def make(root,mode):
    if mode not in ('init','forward'):
        raise GateError('C62 mode invalid')
    old,binary,stat=original()
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy or \
       any(stat[key]!=snapshot['model_stat'][other] for key,other in
           (('dev','dev'),('ino','inode'),('size','size_bytes'),('mtime_ns','mtime_ns'))):
        raise GateError('C62 fresh inventory/model identity changed')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP,
                                               start_mode='CAPACITY_ADMISSION_START')
    command=list(old['config']['server_command'])
    command[0]=str(binary)
    command[command.index('-ngl')+1]='14'
    if command[command.index('-c')+1]!='8192' or \
       command[command.index('-ub')+1]!='32' or \
       command[command.index('--moe-stream-cache')+1]!='32s':
        raise GateError('C62 session control parameters changed')
    if mode=='init':
        tasks=[]
        request={'mode':'init-only','attempts':1}
        timeout=120
    else:
        source=strict_json(INPUT.read_text())['short513']
        task={'id':'c62-p14-cold513','category':'synthetic-capacity',
              'prompt':source['prompt'],'cache_prompt':False}
        tasks=[(task['id'],task)]
        request={'mode':'short-forward-admission','attempts':1,
                 'max_tokens':4,'temperature':0,'seed':42,
                 'per_request_timeout_s':300}
        timeout=420
    config={'server_command':command,'explicit_env':dict(old['config']['explicit_env']),
            'suite':'c62'+mode,'task_ids':[x[0] for x in tasks],
            'request_policy':request,'total_timeout_s':timeout,
            'output_root':str((root/'raw').resolve()),'backend_root':str(BACKEND),
            'n_ctx':8192,'stream_requests':False,
            'pretokenize':mode=='forward','enforce_output_reserve':mode=='forward'}
    identity=dict(old['protocol']['identity'])
    identity.update(config_sha256=server.digest(config),
                    workload_sha256=server.digest(tasks),
                    input_sha256={key:server.digest(value) for key,value in tasks})
    protocol={'schema_version':'c62-protocol-v1','campaign_id':root.name,
              'protocol_id':f'c62-p14-{mode}-v1','identity':identity,
              'expected_request_ids':[x[0] for x in tasks],
              'limits':{'max_gap_s':3,'boundary_s':2},'resources':resources,
              'c62':{'mode':mode,'n_gpu_layers':14,'n_ctx':8192,'slots':32,'ubatch':32,
                     'model_stat':stat,'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
                     'binary_sha256':sha256(binary),'libraries_sha256':backend_library_hashes(str(binary),BACKEND),
                     'server_runner_sha256':sha256(server.__file__),
                     'runner_sha256':sha256(__file__),'input_sha256':sha256(INPUT),
                     'accounting_sha256':sha256(ACCOUNT),
                     'claim':'capacity admission only; no performance/fidelity/quality claim',
                     'prompt_tokens_admission_band':[480,540] if mode=='forward' else None,
                     'publication':'local only'}}
    validate_resource_protocol(protocol)
    return protocol,config,tasks


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new C62 root/raw required')
    for mode,_ in ARMS:
        protocol,_,_=make(root,mode)
        write_new(root/f'protocol-{mode}.json',protocol)
    write_new(root/'preflight.json',{'schema':'c62-freeze-v1',
       'utc':datetime.now(timezone.utc).isoformat(),
       'snapshot_sha256':sha256(root/'snapshot.json'),
       'resource_policy_sha256':sha256(root/'resource-policy.json'),
       'init_protocol_sha256':sha256(root/'protocol-init.json'),
       'forward_protocol_sha256':sha256(root/'protocol-forward.json'),
       'status':'FROZEN_NOT_MEASURED'})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','root':str(root)}))


def inside(root,mode,commit):
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):
        raise GateError('C62 measurement tree not clean')
    protocol,config,tasks=make(root,mode)
    if protocol!=strict_json((root/f'protocol-{mode}.json').read_text()):
        raise GateError('C62 protocol/source identity changed')
    no_other_model()
    run_id=dict(ARMS)[mode]
    args=SimpleNamespace(model='target120b',suite='c62'+mode,
                         run_id=run_id,protocol=root/f'protocol-{mode}.json')
    return server.run(args,protocol,config,tasks,MODEL)


def verify(root,mode,scope_rc):
    run_id=dict(ARMS)[mode]
    receipt={'schema':'c62-arm-receipt-v1','run_id':run_id,'mode':mode,
             'scope_returncode':scope_rc,'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    path=root/'raw'/f'{run_id}.json'
    if not path.is_file():
        receipt['reason']='server raw receipt absent'
        return receipt
    receipt['raw_sha256']=sha256(path)
    raw=strict_json(path.read_text())
    receipt['returncode']=raw.get('returncode')
    receipt['stop_reasons']=raw.get('stop_reasons')
    receipt['elapsed_s']=raw.get('elapsed_s')
    if scope_rc!=0:
        receipt['reason']='scope or server runner nonzero'
        return receipt
    protocol,config,_=make(root,mode)
    try:
        samples=[strict_json(x) for x in
                 (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
        maxima=validate_receipt(protocol,config,raw,samples,root,
                run_id=run_id,protocol_filename=f'protocol-{mode}.json',
                expected_results=0 if mode=='init' else 1)
        if mode=='forward':
            prompt=raw['results'][0]['usage']['prompt_tokens']
            if not 480<=prompt<=540:
                raise GateError('C62 prompt token count outside frozen admission band')
            receipt['prompt_tokens']=prompt
            receipt['completion_tokens']=raw['results'][0]['usage']['completion_tokens']
        receipt.update(status='PASS_CAPACITY_ADMISSION',maxima=maxima,
                       sample_count=len(samples))
    except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
        receipt['reason']=f'{type(exc).__name__}: {exc}'
    return receipt


def run(root,commit):
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):
        raise GateError('C62 measurement commit/tree not clean')
    pre=strict_json((root/'preflight.json').read_text())
    if pre['snapshot_sha256']!=sha256(root/'snapshot.json') or \
       pre['resource_policy_sha256']!=sha256(root/'resource-policy.json'):
        raise GateError('C62 inventory changed')
    observed=[]
    for mode,run_id in ARMS:
        protocol,_,_=make(root,mode)
        if protocol!=strict_json((root/f'protocol-{mode}.json').read_text()) or \
           pre[mode+'_protocol_sha256']!=sha256(root/f'protocol-{mode}.json'):
            raise GateError('C62 frozen protocol changed')
        no_other_model()
        command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
                 '-p','MemorySwapMax=0','--','python3','tools/c62_placement_admission.py',
                 'inside',str(root),'--mode',mode,'--measurement-commit',commit]
        process=subprocess.run(command,capture_output=True,text=True,check=False)
        receipt=verify(root,mode,process.returncode)
        receipt['scope_stderr_tail']=process.stderr[-1000:]
        observed.append(receipt)
        print(json.dumps({'run_id':run_id,'status':receipt['status'],
                          'reason':receipt.get('reason'),'maxima':receipt.get('maxima')}),flush=True)
        if receipt['status']!='PASS_CAPACITY_ADMISSION':break
    for receipt in observed:
        write_new(root/(receipt['run_id']+'-receipt.json'),receipt)
    return 0 if len(observed)==2 and all(x['status']=='PASS_CAPACITY_ADMISSION' for x in observed) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('freeze','run','inside'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--mode',choices=('init','forward'))
    parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    elif args.action=='inside':
        if not args.mode or not args.measurement_commit:parser.error('inside needs mode and commit')
        raise SystemExit(inside(root,args.mode,args.measurement_commit))
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
