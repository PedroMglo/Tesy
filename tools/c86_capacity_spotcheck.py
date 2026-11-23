#!/usr/bin/env python3
"""Read-only necessary-condition check for E18; never admits a model."""

import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from c2_gate import GateError

ROOT = Path('results/c86-capacity-spotcheck-20260928T2018Z')
GIB = 2**30
STEP = 256 * 2**20
E18 = 18 * GIB


def meminfo():
    found = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, sep, value = line.partition(':')
        if name in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            parts = value.strip().split()
            if not sep or len(parts) != 2 or parts[1] != 'kB':
                raise GateError('meminfo unit changed')
            found[name] = int(parts[0]) * 1024
    if set(found) != {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'} or \
       found['MemAvailable'] <= 0 or found['MemAvailable'] > found['MemTotal']:
        raise GateError('meminfo incomplete/inconsistent')
    return found


def main():
    if ROOT.exists():
        raise GateError('C86 no-replace root exists')
    before = datetime.now(timezone.utc).isoformat()
    memory = meminfo()
    gpu = subprocess.run(['nvidia-smi',
        '--query-gpu=uuid,memory.used,temperature.gpu,utilization.gpu',
        '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
    after = datetime.now(timezone.utc).isoformat()
    cap_upper = max(0, ((memory['MemAvailable']-2*GIB)//STEP)*STEP)
    status = 'E18_NECESSARY_HEADROOM_ABSENT' if cap_upper < E18 else 'SPOTCHECK_ONLY_NOT_ADMITTED'
    result = {'schema':'c86-capacity-spotcheck-v1','evidence_class':'DIAGNOSTIC_SPOTCHECK',
              'started_utc':before,'ended_utc':after,'memory_bytes':memory,
              'reserve_lower_bound_bytes':2*GIB,
              'cap_upper_from_single_memavailable_sample_bytes':cap_upper,
              'E18_required_bytes':E18,
              'E18_shortfall_lower_bound_bytes':max(0,E18-cap_upper),
              'gpu_query':{'returncode':gpu.returncode,'stdout':gpu.stdout.strip(),
                           'stderr':gpu.stderr.strip()},
              'status':status,'model_loaded':False,
              'limits':['single MemAvailable sample can reject the necessary E18 condition but cannot admit a workload',
                        'external memory variation and ancestor cgroup headroom can lower the admissible cap',
                        'one earlier nvidia-smi query failed transiently; this snapshot is independent']}
    ROOT.mkdir(exist_ok=False)
    with (ROOT/'snapshot.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status':status,'shortfall_bytes':result['E18_shortfall_lower_bound_bytes'],
                      'gpu_query_returncode':gpu.returncode}))


if __name__ == '__main__':
    main()
