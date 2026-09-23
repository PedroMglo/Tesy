"""Opt-in stock llama.cpp launch, NOT Tesy's dynamic expert runtime.

Single immutable model, natural routing, no speculation. Sampling resources
once per second is a guard, not an OOM-proof reservation or formal telemetry.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import doctor, models
from .io import (canonical_path, hash_fd, identity, integer, keys, load_json,
                 require, stable_file)

GiB = 1 << 30


def command(binary: str | Path, model: str, cpu_only: bool) -> list[str]:
    args = [str(binary), '--model', model, '--offline', '--ctx-size', '4096',
            '--threads', '8', '--threads-batch', '8', '--batch-size', '64',
            '--ubatch-size', '64', '--n-predict', '128', '--seed', '1', '--temp', '0',
            '--cache-type-k', 'f16', '--cache-type-v', 'f16', '--load-mode', 'mmap',
            '--fit', 'off', '--no-op-offload', '--conversation', '--jinja']
    return args + (['--gpu-layers', '0'] if cpu_only else ['--gpu-layers', '48', '--cpu-moe'])


def check_resources(host: dict, baseline_swap: int, cpu_only: bool, initial: bool = False,
                    model_bytes: int = 0) -> None:
    mem = host['memory']
    require('MemAvailable_bytes' in mem and 'SwapTotal_bytes' in mem and 'SwapFree_bytes' in mem,
            'required RAM/swap observation unavailable')
    require(mem['MemAvailable_bytes'] >= (model_bytes + 2 * GiB if initial else 4 * GiB),
            'insufficient MemAvailable')
    swap = mem['SwapTotal_bytes'] - mem['SwapFree_bytes']
    require(swap - baseline_swap <= 256 * 2**20, 'swap growth guard exceeded')
    cmax, ccurrent = mem.get('cgroup_memory.max'), mem.get('cgroup_memory.current')
    if cmax is not None:
        require(ccurrent is not None and cmax - ccurrent >= (model_bytes + 2 * GiB if initial else GiB),
                'cgroup memory budget exhausted/unobservable')
    if not cpu_only:
        devices = host['gpu']['devices']
        require(host['gpu']['status'] == 'OBSERVED' and len(devices) == 1, 'single GPU observation required')
        gpu = devices[0]
        require('RTX 4060 Laptop' in gpu['name'], 'GPU differs from laptop profile')
        require(gpu['temperature_c'] <= 85, 'GPU temperature guard exceeded')
        require(gpu['used_bytes'] <= gpu['total_bytes'] - GiB, 'GPU reserve exhausted')


def execute(model: dict, path: Path, binary: Path, backend_lock: Path,
            cpu_only: bool, seconds: int) -> int:
    integer(seconds, 'duration', 1, 1800)
    require(sys.platform.startswith('linux'), 'baseline FD handoff requires Linux')
    require(model['architecture'] == 'qwen3moe', 'stock profile only supports initial Qwen3 MoE')
    models.verify(model, path)
    lock = load_json(backend_lock)
    keys(lock, {'schema', 'repository', 'commit', 'status', 'observed_date'}, 'backend lock')
    require(lock['schema'] == 'tesy.backend-lock.v1', 'backend lock schema differs')
    binary = canonical_path(binary)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('LLAMA_ARG_', 'HF_', 'HUGGING_FACE_', 'GGML_'))}
    env['HF_HUB_OFFLINE'] = '1'
    env['OMP_NUM_THREADS'] = '8'
    proc = None
    # Hold the model FD through the child; the model pathname cannot be swapped.
    with stable_file(binary) as (bfd, bst), stable_file(path) as (mfd, mst):
        require(mst.st_size == model['bytes'] and hash_fd(mfd, mst.st_size) == model['sha256'],
                'model changed after metadata inspection')
        binary_sha = hash_fd(bfd, bst.st_size)
        version = subprocess.run([str(binary), '--version'], capture_output=True, text=True,
                                 timeout=10, check=True, env=env)
        require(lock['commit'][:7] in version.stdout + version.stderr,
                'binary version does not match locked source commit')
        help_result = subprocess.run([str(binary), '--help'], capture_output=True, text=True,
                                    timeout=10, check=True, env=env)
        for flag in ('--cpu-moe', '--offline', '--no-op-offload', '--load-mode', '--fit'):
            require(flag in help_result.stdout + help_result.stderr, f'backend missing {flag}')
        host = doctor.snapshot()
        mem = host['memory']
        swap_start = mem.get('SwapTotal_bytes', 0) - mem.get('SwapFree_bytes', 0)
        check_resources(host, swap_start, cpu_only, True, model['bytes'])
        require(identity(os.fstat(bfd)) == identity(bst), 'binary changed before launch')
        print(f'STOCK_BASELINE_ONLY binary_sha256={binary_sha} optimized_tesy=false', file=sys.stderr)
        argv = command(binary, f'/proc/self/fd/{mfd}', cpu_only)
        started = time.monotonic()
        try:
            proc = subprocess.Popen(argv, env=env, pass_fds=(mfd,), start_new_session=True)
            while proc.poll() is None:
                require(time.monotonic() - started < seconds, 'baseline duration budget exceeded')
                check_resources(doctor.snapshot(), swap_start, cpu_only)
                time.sleep(1)
            require(proc.returncode == 0, f'stock process failed: {proc.returncode}; no retry')
            return proc.returncode
        finally:
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
