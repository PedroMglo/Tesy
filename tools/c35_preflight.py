#!/usr/bin/env python3
"""Fresh host, model and isolated backend inventory for C35."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess

from c2_gate import GateError, strict_json
from c8_observer_runner import model_stat
from c9_server_admission import MODEL, MODEL_SHA
from c18_cpu_telemetry import capture as cpu_capture
from c24_preflight import scope_test
from c35_template_date import ROOT, BACKEND, BINARY
from run_bounded import backend_library_hashes, sha256


def call(*args):
    return subprocess.check_output(args,text=True,timeout=15).strip()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    root=args.root
    if root != ROOT or not (root/'raw').is_dir() or not (root/'protocol.json').is_file():
        raise GateError('C35 output root/protocol missing')
    high=strict_json((root/'protocol.json').read_text())
    if git_head := call('git','-C',str(BACKEND),'rev-parse','HEAD'):
        if git_head != high['backend_candidate_commit'] or \
                call('git','-C',str(BACKEND),'status','--porcelain'):
            raise GateError('C35 backend source differs from freeze')
    if not BINARY.is_file() or not backend_library_hashes(str(BINARY),BACKEND):
        raise GateError('C35 binary/libraries unavailable')
    prior=strict_json(Path('results/c20-prefix-pairs-20260927T1857Z/preflight.json').read_text())['model']
    if prior['sha256'] != MODEL_SHA or prior['stat'] != model_stat():
        raise GateError('C35 model differs from verified full SHA')
    sensors=strict_json(call('sensors','-j'))
    gpu=call('nvidia-smi','--query-gpu=name,memory.total,memory.used,temperature.gpu,driver_version',
             '--format=csv,noheader,nounits')
    apps=call('nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory',
              '--format=csv,noheader')
    scope=scope_test()
    cpu=cpu_capture()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',18367))
    memory={key:int(value.split()[0])*1024 for key,value in
            (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
            if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree')}
    free=os.statvfs(root).f_bavail*os.statvfs(root).f_frsize
    gpu_parts=[x.strip() for x in gpu.split(',')]
    power='AC' if Path('/sys/class/power_supply/AC0/online').read_text().strip()=='1' else 'BATTERY'
    status='READY_FOR_IDLE_ADMISSION' if scope['status']=='PASS' and not apps and \
           cpu['processor_cooling_max_state']==0 and power=='AC' and \
           float(gpu_parts[2])<7000 and memory['MemAvailable']>=6*2**30 and \
           free>20*2**30 else 'BLOCKED_HOST_OR_RESOURCES'
    report={'schema':'c35-preflight-v1','utc':datetime.now(timezone.utc).isoformat(),
            'guard_status':status,'model':{'path':str(MODEL),'sha256':MODEL_SHA,
                                         'stat':model_stat(),
                                         'full_sha_provenance':'C20 full model SHA, current stat exact match'},
            'backend':{'root':str(BACKEND),'head':git_head,
                       'tree':call('git','-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
                       'dirty':'','binary_sha256':sha256(BINARY),
                       'library_sha256':backend_library_hashes(str(BINARY),BACKEND)},
            'cpu_diagnostics':cpu,'cooling_condition':'changed_physical_placement (owner report)',
            'ambient_temperature':'UNKNOWN','power_source':power,
            'power_profile':call('powerprofilesctl','get'),
            'fan_profile_if_observable':'RPM observed; policy not directly readable',
            'sensors':sensors,'gpu_csv':gpu,'gpu_compute_apps':apps,
            'memory':memory,'free_bytes':free,
            'filesystem':call('findmnt','-T',str(root),'-no','TARGET,SOURCE,FSTYPE'),
            'host_kernel':call('uname','-r'),
            'scope_model_free_test':scope,'port_18367_free':True,
            'cpu_policy':{'warning_c':95,'stop_c':100},
            'resource_guards':high['resource_guards']}
    with (root/'preflight.json').open('x') as out:
        json.dump(report,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    print(json.dumps({'status':status,'gpu':gpu,'memory_available_bytes':memory['MemAvailable']}))
    return 0 if status=='READY_FOR_IDLE_ADMISSION' else 1


if __name__=='__main__':
    raise SystemExit(main())
