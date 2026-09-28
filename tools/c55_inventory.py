#!/usr/bin/env python3
"""Model-free physical inventory and 60-second host admission baseline."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

from c2_gate import GateError, strict_json
from host_resource_policy import derive_policy, ResourcePolicyError, GIB
from run_bounded import sha256
from c9_server_admission import MODEL


def call(*argv):
    return subprocess.check_output(argv,text=True,timeout=15).strip()

def optional_call(*argv):
    try:return {'status':'SUPPORTED','output':call(*argv)}
    except (OSError,subprocess.SubprocessError) as exc:
        return {'status':'UNAVAILABLE','error':str(exc)}

def memory():
    return {key:int(value.split()[0])*1024 for key,value in
            (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
            if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree')}

def psi():
    line=next(row for row in Path('/proc/pressure/memory').read_text().splitlines()
              if row.startswith('full '))
    return {k:float(v) if k!='total' else int(v) for k,v in
            (part.split('=',1) for part in line.split()[1:])}

def cpu_identity():
    first=Path('/proc/cpuinfo').read_text().split('\n\n',1)[0]
    keys={k.strip():v.strip() for k,v in (line.split(':',1) for line in first.splitlines()
                                           if ':' in line)}
    return {'model':keys['model name'],'family':int(keys['cpu family']),
            'model_id':int(keys['model'])}

def ancestor_headroom(memtotal, *, root=Path('/sys/fs/cgroup'), rel=None):
    cg=rel if rel is not None else next(
        line.split('::',1)[1] for line in Path('/proc/self/cgroup').read_text().splitlines()
        if line.startswith('0::'))
    path=root/cg.lstrip('/')
    headroom=memtotal; rows=[]
    while path==root or root in path.parents:
        max_file=path/'memory.max'
        current_file=path/'memory.current'
        if not max_file.is_file() or not current_file.is_file():
            if path != root:
                raise GateError('non-root ancestor cgroup accounting absent')
            rows.append({'path':str(path),'memory_max':'UNBOUNDED_ROOT',
                         'memory_current':None})
            break
        cap=max_file.read_text().strip()
        current=int(current_file.read_text().strip())
        if cap!='max':
            remaining=int(cap)-current
            headroom=min(headroom,max(0,remaining))
        rows.append({'path':str(path),'memory_max':cap,'memory_current':current})
        if path==root:break
        path=path.parent
    return headroom,rows

def mounts(paths):
    result={}; involved={}
    for label,path in paths.items():
        if not path.exists():raise GateError('inventory path absent: '+str(path))
        source,target,fs=call('findmnt','-T',str(path),'-no','SOURCE,TARGET,FSTYPE').split(None,2)
        result[label]={'path':str(path),'source':source,'target':target,'fstype':fs}
        match=re.search(r'(nvme\d+)n\d+',source)
        if match:
            controller=match.group(1)
            sys=Path('/sys/class/nvme')/controller
            if not sys.is_dir():raise GateError('NVMe sysfs absent')
            bdf=Path(os.path.realpath(sys/'device')).name
            involved[controller]={'bdf':bdf,'model':(sys/'model').read_text().strip(),
                                  'firmware':(sys/'firmware_rev').read_text().strip()}
        elif fs!='tmpfs':
            raise GateError('storage backing device not mapped to NVMe')
    if not involved:raise GateError('no NVMe controller mapped')
    return result,involved

def power():
    sources=[]; batteries=[]
    for item in sorted(Path('/sys/class/power_supply').iterdir()):
        kind=(item/'type').read_text().strip()
        if kind in ('Mains','USB','USB_C','USB_PD') and (item/'online').is_file() and \
           (item/'online').read_text().strip()=='1':
            sources.append(item.name)
        if kind=='Battery' and (item/'status').is_file():
            batteries.append({'name':item.name,'status':(item/'status').read_text().strip()})
    return {'source':'AC' if sources else 'BATTERY','online_sources':sources,
            'profile':call('powerprofilesctl','get'),'batteries':batteries}

def run(root):
    if not root.is_dir() or (root/'snapshot.json').exists() or (root/'resource-policy.json').exists():
        raise GateError('inventory root must be new/no-replace')
    model=Path(MODEL)
    paths={'model':model,'raw':root,'workspace':Path('/tmp')}
    mapped,involved=mounts(paths)
    start=time.monotonic(); baseline=[]
    while True:
        t=time.monotonic()-start
        m=memory();p=psi()
        baseline.append({'elapsed_s':t,'MemAvailable':m['MemAvailable'],
                         'psi_full_avg10':p['avg10']})
        if t>=60:break
        time.sleep(max(0,1-(time.monotonic()-start-t)))
    gaps=[b['elapsed_s']-a['elapsed_s'] for a,b in zip(baseline,baseline[1:])]
    if len(baseline)<60 or max(gaps)>1.5:
        raise GateError('60-second inventory cadence incomplete')
    m=memory(); headroom,ancestors=ancestor_headroom(m['MemTotal'])
    m['MemAvailable_min']=min(x['MemAvailable'] for x in baseline)
    m['MemAvailable_max']=max(x['MemAvailable'] for x in baseline)
    m['ancestor_headroom_bytes']=headroom
    snapshot={'schema':'c55-host-snapshot-v1','utc':datetime.now(timezone.utc).isoformat(),
              'gpu_csv':call('nvidia-smi','--query-gpu=uuid,pci.bus_id,name,memory.total,memory.used,temperature.gpu,driver_version',
                             '--format=csv,noheader,nounits'),
              'gpu_temperature_query':call('nvidia-smi','-q','-d','TEMPERATURE'),
              'gpu_power_query':optional_call('nvidia-smi','--query-gpu=power.draw,power.limit,enforced.power.limit',
                                              '--format=csv,noheader,nounits'),
              'sensors':strict_json(call('sensors','-j')),
              'cpu_identity':cpu_identity(),'involved_nvme':involved,
              'mounts':mapped,'power':power(),'memory':m,
              'psi':{'full_avg10':psi()['avg10'],'raw':psi()},
              'ancestors':ancestors,'baseline':baseline,
              'model_stat':{'dev':model.stat().st_dev,'inode':model.stat().st_ino,
                            'size_bytes':model.stat().st_size,'mtime_ns':model.stat().st_mtime_ns},
              'storage_free_bytes':os.statvfs(root).f_bavail*os.statvfs(root).f_frsize}
    try:policy=derive_policy(snapshot=snapshot)
    except ResourcePolicyError as exc:
        with (root/'snapshot.json').open('x') as f:
            json.dump(snapshot,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
        raise GateError('inventory policy rejected: '+str(exc)) from exc
    with (root/'snapshot.json').open('x') as f:
        json.dump(snapshot,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    with (root/'resource-policy.json').open('x') as f:
        json.dump(policy,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps({'status':'REPRODUCED_MODEL_FREE','snapshot_sha256':sha256(root/'snapshot.json'),
                      'cap_max_bytes':policy['memory']['cap_max_bytes'],
                      'gpu_stop_c':policy['gpu']['stop_c'],
                      'gpu_thermal_status':policy['gpu']['status']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args()
    run(args.root)
