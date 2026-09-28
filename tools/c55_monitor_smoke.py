#!/usr/bin/env python3
"""Exercise the prospective monitor in a real bounded scope without a model."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time

from c2_gate import GateError,strict_json
from c2_server_run import process_identity
from host_resource_policy import (RuntimeGuard,derive_policy,
                                  freeze_protocol_resource_limits,host_pressure,live_power)
from run_bounded import cgroup_state,gpu_state,mem_available,proc_status,thermal_state

def run(root):
    out=root/'monitor-smoke.json'
    if out.exists():raise GateError('monitor smoke no-replace')
    policy=derive_policy(snapshot=strict_json((root/'snapshot.json').read_text()))
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=18*2**30)
    protocol={'limits':{'max_gap_s':3},'resources':resources}
    start=cgroup_state()
    if not start or start['memory_max']!=18*2**30 or start['swap_max']!=0:
        raise GateError('model-free scope cap/swap invalid')
    gate=RuntimeGuard(protocol,start)
    samples=[]
    child=subprocess.Popen(['/usr/bin/sleep','8'],start_new_session=True)
    try:
        identity=process_identity(child.pid)
        if identity['cgroup_path']!=start['path']:
            raise GateError('child not in frozen scope')
        t0=time.monotonic()
        while child.poll() is None:
            stamp=time.monotonic()-t0
            gpu=gpu_state(prospective=True); thermal=thermal_state(prospective=True)
            cg=cgroup_state();proc=proc_status(child.pid);available=mem_available()
            if not all((gpu,thermal,cg,proc,available)):
                raise GateError('model-free live sensor absent')
            sample={'elapsed_s':stamp,'pid':child.pid,'process_identity':process_identity(child.pid),
                    'gpu':gpu,'thermal':thermal,'cgroup':cg,'proc':proc,
                    'mem_available_bytes':available,
                    'resource_observation':{'host_psi_full_avg10':host_pressure(),
                                            'power':live_power()}}
            reason=gate.check(sample)
            if reason:raise GateError('model-free monitor stopped: '+reason)
            samples.append({'elapsed_s':stamp,'cpu_c':thermal['cpu_tctl_c'],
                            'gpu_c':gpu['temperature_c'],
                            'nvme_c':thermal['nvme_composite_by_sensor'][resources['nvme'][0]['sensor']],
                            'mem_available_bytes':available,
                            'psi_full_avg10':sample['resource_observation']['host_psi_full_avg10']})
            time.sleep(max(0,1-(time.monotonic()-t0-stamp)))
        if child.returncode!=0:raise GateError('model-free child exit invalid')
    finally:
        if child.poll() is None:
            child.terminate();child.wait(timeout=5)
    gaps=[b['elapsed_s']-a['elapsed_s'] for a,b in zip(samples,samples[1:])]
    if len(samples)<5 or max(gaps)>resources['telemetry']['max_gap_s']:
        raise GateError('model-free monitor cadence invalid')
    row={'schema':'c55-model-free-monitor-v1','status':'REPRODUCED_MODEL_FREE',
         'utc':datetime.now(timezone.utc).isoformat(),'scope':start['path'],
         'memory_max_bytes':start['memory_max'],'swap_max_bytes':start['swap_max'],
         'child_identity':identity,'sample_count':len(samples),'max_gap_s':max(gaps),
         'samples':samples,'model_loaded':False}
    with out.open('x') as f:json.dump(row,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps({'status':row['status'],'samples':len(samples),'max_gap_s':max(gaps)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();run(a.root)
