"""Full c2 launch and two HTTP requests with a C122 trigger, without weights."""

import json
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c118_start_inventory import collect
from host_resource_policy import digest
from run_bounded import sha256


def run(campaign_root):
    root=campaign_root/'model-free-smoke'
    root.mkdir();(root/'raw').mkdir()
    policy=strict_json((campaign_root/'resource-policy.json').read_text())
    (root/'resource-policy.json').write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n')
    cap=18*2**30
    cg=server.cgroup_state()
    if not cg or cg['memory_max']!=cap or cg['swap_max']!=0:
        raise GateError('C122 model-free E18 scope missing')
    run_id='c122-smoke01'
    power={k:policy['power'][k] for k in ('source','profile')}
    inv=collect(root,run_id,policy=policy,cap_bytes=cap,
                expected_power=power,duration_s=60)
    inv_path=root/'raw'/f'{run_id}.start-inventory.receipt.json'
    inv_path.write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n')
    dummy=root/'dummy-model.bin';dummy.write_bytes(b'c122 model free smoke')
    backend=root/'empty-backend';backend.mkdir()
    trigger=root/'raw'/f'{run_id}.trace-trigger.json'
    config={'output_root':str((root/'raw').resolve()),
            'server_command':['python3','tools/c122_smoke_server.py'],
            'backend_root':str(backend),'explicit_env':{
                'TESY_C122_TRACE_TRIGGER_FILE':str(trigger.resolve())},
            'suite':'c122smoke','task_ids':['first','second'],
            'request_policy':{'max_tokens':1,'per_request_timeout_s':5},
            'trace_trigger_request_id':'second',
            'record_monotonic_request_markers':True,'total_timeout_s':25}
    reference=strict_json((campaign_root/'protocols'/'c122-c75-warm153.json').read_text())
    protocol={'schema_version':'c122-model-free-smoke-v1',
              'campaign_id':root.name,'protocol_id':run_id,
              'resources':reference['resources'],'limits':reference['limits'],
              'expected_request_ids':['first','second'],
              'identity':{'model_sha256':sha256(dummy),'library_sha256':{},
                          'config_sha256':digest(config)},
              'trace':{'request_marker_schema':'c85-request-monotonic-v1',
                       'expert_trace_schema':'c122-expert-decode-v1'},
              'start_inventory':{'schema':'c120-start-inventory-v1',
                 'duration_s':60,'max_age_s':3,
                 'policy_sha256':sha256(root/'resource-policy.json')}}
    protocol_path=root/'protocol.json'
    protocol_path.write_text(json.dumps(protocol,indent=2,sort_keys=True)+'\n')
    tasks=[(name,{'id':name,'category':'model-free',
                  'messages':[{'role':'user','content':name}]})
           for name in ('first','second')]
    args=SimpleNamespace(run_id=run_id,protocol=protocol_path,
                         suite='c122smoke',model='target120b')
    try:
        code=server.run(args,protocol,config,tasks,dummy)
        raw=strict_json((root/'raw'/f'{run_id}.json').read_text())
        marker=[json.loads(line) for line in
                (root/'raw'/f'{run_id}.request-markers.jsonl').read_text().splitlines()]
        observed=[r['message']['content'] for r in raw['results']]
        trigger_row=strict_json(trigger.read_text())
        valid=code==0 and observed==['ABSENT','PRESENT'] and \
              trigger_row['request_id']=='second' and \
              trigger_row['mono_ns']<=next(m['mono_ns'] for m in marker if
                  m['request_id']=='second' and m['kind']=='REQUEST_START')
        row={'schema':'c122-model-free-smoke-v1',
             'status':'PASS_TRIGGER_ENTRYPOINT' if valid else 'FAIL_TRIGGER_ENTRYPOINT',
             'observed':observed,'trigger_sha256':sha256(trigger),
             'raw_sha256':sha256(root/'raw'/f'{run_id}.json'),
             'model_weights_loaded':False}
    except Exception as exc:
        row={'schema':'c122-model-free-smoke-v1','status':'FAIL_TRIGGER_ENTRYPOINT',
             'reason':f'{type(exc).__name__}: {exc}','model_weights_loaded':False}
    (root/'result.json').write_text(json.dumps(row,indent=2,sort_keys=True)+'\n')
    print(json.dumps(row))
    return 0 if row['status']=='PASS_TRIGGER_ENTRYPOINT' else 1


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path)
    a=ap.parse_args();raise SystemExit(run(a.root.resolve()))
