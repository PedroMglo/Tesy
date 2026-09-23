"""Read-only host observation. No model, CUDA context, service or mount changes."""
from __future__ import annotations

import datetime as dt
import os
import platform
import shutil
import subprocess
from pathlib import Path


def read(path: str) -> str | None:
    try:
        return Path(path).read_text()[:65536]
    except OSError:
        return None


def memory() -> dict:
    result = {}
    for line in (read('/proc/meminfo') or '').splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].rstrip(':') in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            result[parts[0].rstrip(':') + '_bytes'] = int(parts[1]) * 1024
    for name in ('memory.max', 'memory.current'):
        value = read('/sys/fs/cgroup/' + name)
        result['cgroup_' + name] = int(value.strip()) if value and value.strip().isdigit() else None
    return result


def gpu() -> dict:
    binary = shutil.which('nvidia-smi')
    if not binary:
        return {'status': 'NOT_AVAILABLE', 'devices': []}
    try:
        proc = subprocess.run([binary, '--query-gpu=name,uuid,memory.total,memory.used,temperature.gpu',
                               '--format=csv,noheader,nounits'], capture_output=True,
                              text=True, timeout=5, check=True)
        devices = []
        for line in proc.stdout.splitlines():
            parts = [s.strip() for s in line.split(',')]
            if len(parts) != 5:
                raise ValueError('unexpected nvidia-smi row')
            devices.append({'name': parts[0], 'uuid': parts[1],
                            'total_bytes': int(parts[2]) * 2**20,
                            'used_bytes': int(parts[3]) * 2**20,
                            'temperature_c': int(parts[4])})
        return {'status': 'OBSERVED', 'devices': devices}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'status': 'NOT_AVAILABLE', 'devices': [], 'error': str(exc)}


def snapshot() -> dict:
    cpu = read('/proc/cpuinfo') or ''
    names = [line.split(':', 1)[1].strip() for line in cpu.splitlines() if line.startswith('model name')]
    return {'schema': 'tesy.host-observation.v1', 'classification': 'OBSERVED_THIS_HOST_ONLY',
            'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'platform': platform.platform(), 'cpu': names[0] if names else platform.processor(),
            'logical_cpus': os.cpu_count(),
            'affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
            'memory': memory(), 'gpu': gpu(),
            'tools': {name: shutil.which(name) for name in ('git', 'cmake', 'c++', 'nvcc', 'nvidia-smi', 'graphify')},
            'qualification': False, 'model_opened': False,
            'warning': 'No laptop match, performance, storage bandwidth or thermal stability certified.'}
