#!/usr/bin/env python3
"""One short physical policy canary on the unchanged C52b session backend."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError,strict_json
from c9_server_admission import validate_receipt
from host_resource_policy import (GIB,derive_policy,freeze_protocol_resource_limits,
                                  validate_resource_protocol)
from run_bounded import backend_library_hashes,sha256

REPO=Path(__file__).resolve().parents[1]
OLD=REPO/'results/c52b-assistant-history-sustained-20260928T1132Z'
BACKEND=Path('/tmp/tesy-c35-backend-20260928')
MODEL=Path('/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf')
CAP=18*GIB
RUN_ID='c58-p12-policy-canary01'
TASK={'id':'c58-synthetic-canary01','category':'synthetic-canary',
      'prompt':'Reply with OK.'}

def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()

def write_new(path,obj):
    with path.open('x') as out:
        json.dump(obj,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')

def original():
    manifest=strict_json((OLD/'manifest.json').read_text())
    old_preflight=OLD/'raw/c52b-p12-assistant-history01.preflight.json'
    expected=manifest['raw_sha256'][old_preflight.name]['sha256']
    if sha256(old_preflight)!=expected:
        raise GateError('historical C52b preflight SHA changed')
    pre=strict_json(old_preflight.read_text())
    identity=pre['protocol']['identity']
    binary=BACKEND/'build-c35-gcc15/bin/llama-server'
    if git('-C',str(BACKEND),'rev-parse','HEAD')!=identity['backend_sha'] or \
       git('-C',str(BACKEND),'status','--porcelain') or \
       sha256(binary)!=identity['binary_sha256'] or \
       backend_library_hashes(str(binary),BACKEND)!=identity['library_sha256']:
        raise GateError('C52b backend binary or libraries changed')
    stat=os.stat(MODEL)
    frozen=pre['model_stat_before']
    current={'dev':stat.st_dev,'ino':stat.st_ino,'size':stat.st_size,
             'mtime_ns':stat.st_mtime_ns}
    if current!=frozen or current['size']!=63387346208:
        raise GateError('model stat changed since verified C52b model SHA')
    return pre,binary,current

def make(root):
    old,binary,model_stat=original()
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy:
        raise GateError('fresh inventory/policy mismatch')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    config={'server_command':old['config']['server_command'],
            'explicit_env':old['config']['explicit_env'],'suite':'c58canary',
            'task_ids':[TASK['id']],
            'request_policy':{'mode':'synthetic-short-canary','attempts':1,
                              'max_tokens':1,'temperature':0,'seed':42,
                              'per_request_timeout_s':180},
            'total_timeout_s':300,'output_root':str((root/'raw').resolve()),
            'backend_root':str(BACKEND),'n_ctx':8192,'stream_requests':False}
    identity=dict(old['protocol']['identity'])
    identity['config_sha256']=server.digest(config)
    identity['workload_sha256']=server.digest([TASK])
    identity['input_sha256']={'c58-synthetic-canary01':server.digest(TASK)}
    protocol={'schema_version':'c58-protocol-v1','campaign_id':root.name,
              'protocol_id':'c58-policy-canary-short-v1',
              'identity':identity,'expected_request_ids':[TASK['id']],
              'limits':{'max_gap_s':3,'boundary_s':2},'resources':resources,
              'c58':{'model_stat':model_stat,
                     'backend_tree':git('-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
                     'runner_sha256':sha256(__file__),
                     'claim':'policy and load/short-forward canary only; no speedup or quality claim'}}
    validate_resource_protocol(protocol)
    return protocol,config

def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new root/raw required')
    protocol,config=make(root)
    write_new(root/'protocol.json',protocol)
    write_new(root/'preflight.json',{'schema':'c58-freeze-preflight-v1',
        'utc':datetime.now(timezone.utc).isoformat(),
        'inventory_snapshot_sha256':protocol['resources']['snapshot_sha256'],
        'inventory_file_sha256':sha256(root/'snapshot.json'),
        'resource_policy_file_sha256':sha256(root/'resource-policy.json'),
        'backend_commit':protocol['identity']['backend_sha'],
        'binary_sha256':protocol['identity']['binary_sha256'],
        'model_stat':protocol['c58']['model_stat'],
        'selected_cap_bytes':CAP,'selected_run_id':RUN_ID,
        'status':'FROZEN_NOT_MEASURED'})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','root':str(root),'cap':CAP}))

def run(root,measurement_commit):
    if git('rev-parse','HEAD')!=measurement_commit or git('status','--porcelain'):
        raise GateError('measurement commit/tree not clean')
    protocol,config=make(root)
    if strict_json((root/'protocol.json').read_text())!=protocol:
        raise GateError('protocol differs from committed freeze')
    if sha256(root/'snapshot.json')!=strict_json((root/'preflight.json').read_text())['inventory_file_sha256']:
        raise GateError('inventory file changed')
    args=SimpleNamespace(run_id=RUN_ID,protocol=root/'protocol.json',
                         suite='c58canary',model='target120b')
    failure=None
    try:
        code=server.run(args,protocol,config,[(TASK['id'],TASK)],MODEL)
        raw=strict_json((root/'raw'/f'{RUN_ID}.json').read_text())
        samples=[strict_json(line) for line in
                 (root/'raw'/f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
        maxima=validate_receipt(protocol,config,raw,samples,root,
                                run_id=RUN_ID,expected_results=1)
        if code!=0:raise GateError('runner exit failure')
        if os.stat(MODEL).st_mtime_ns!=protocol['c58']['model_stat']['mtime_ns']:
            raise GateError('model changed during canary')
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}'
        raw=locals().get('raw')
        maxima=None
    status='PASS_POLICY_CANARY_TESTED_SCOPE' if failure is None else 'FAIL_RESOURCES_OR_EVIDENCE'
    decision={'schema':'c58-decision-v1','status':status,'reason':failure,
              'measurement_commit':measurement_commit,'run_id':RUN_ID,
              'model_loaded':bool(raw and raw.get('preflight',{}).get('ready_elapsed_s')),
              'completed_requests':len(raw['results']) if raw else 0,
              'stop_reasons':raw.get('stop_reasons') if raw else None,
              'maxima':maxima,'claim_limit':'one synthetic one-token API request, no speedup/quality claim',
              'C48':'FAIL_SAME_PROFILE_FIDELITY_UNCHANGED',
              'next_action':'C57 targeted numeric boundary if pass; inspect actual failure if fail',
              'default_changed':False}
    write_new(root/'decision.json',decision)
    print(json.dumps({'status':status,'reason':failure,'maxima':maxima},allow_nan=False))
    return 0 if failure is None else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('freeze','run'))
    parser.add_argument('root',type=Path);parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    root=args.root.resolve()
    if args.mode=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('--measurement-commit required')
        raise SystemExit(run(root,args.measurement_commit))
