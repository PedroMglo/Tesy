#!/usr/bin/env python3
"""Bounded 8K full-SWA server admission using the repaired C2 server monitor."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c7_timing_runner import cool_start
from c8_observer_runner import model_stat, program_physical_consumed
from run_bounded import backend_library_hashes, relevant_environment, sha256

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path('/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming')
MODEL = Path('/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf')
MODEL_SHA = '582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d'
RUN_ID = 'c9-g1-init'
PORT = 18367


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def environment():
    for key in ('LLAMA_MOE_STREAM_NO_PRELOAD', 'TESY_CPU_FA_PREFILL_VEC_COMPAT', 'LD_PRELOAD'):
        os.environ.pop(key, None)
    if relevant_environment(os.environ):
        raise GateError('unfrozen relevant environment')


def configuration(root):
    binary = BACKEND / 'build-gcc15/bin/llama-server'
    if not binary.is_file() or not MODEL.is_file():
        raise GateError('server binary or existing model missing')
    libs = backend_library_hashes(str(binary), BACKEND)
    if not libs:
        raise GateError('server backend libraries unavailable')
    command = [str(binary), '-m', str(MODEL), '--host', '127.0.0.1', '--port', str(PORT),
               '-ngl', '8', '-c', '8192', '-np', '1', '-b', '256', '-ub', '32',
               '-t', '8', '-tb', '8', '--no-warmup', '--no-webui', '-lv', '3',
               '--no-mmap', '--direct-io', '--no-repack', '--no-op-offload',
               '--moe-stream', '--moe-stream-cache', '32s',
               '--moe-stream-io-threads', '4', '--moe-stream-direct',
               '--swa-full', '--flash-attn', 'on', '--cache-type-k', 'f16',
               '--cache-type-v', 'f16', '--kv-offload', '--kv-unified',
               '--cache-prompt', '--cache-reuse', '0', '--cache-ram', '0',
               '--ctx-checkpoints', '0', '--no-cache-idle-slots',
               '--no-context-shift', '--fit', 'off',
               '--chat-template-kwargs', '{"reasoning_effort":"medium"}']
    config = {'server_command': command, 'explicit_env': {}, 'suite': 'c9init',
              'task_ids': [], 'request_policy': {'mode': 'init-only', 'attempts': 1},
              'total_timeout_s': 120, 'output_root': str((root / 'raw').resolve()),
              'backend_root': str(BACKEND)}
    contract = root / 'usage-contract.json'
    limits = {'memory_max_bytes': int(16.5 * 2**30), 'rss_max_bytes': 16 * 2**30,
              'gpu_max_mib': 6500, 'min_mem_available_bytes': 6 * 2**30,
              'cpu_max_c': 95, 'gpu_max_c': 80, 'nvme_max_c': 70,
              'max_gap_s': 3, 'boundary_s': 2,
              'min_elapsed_s': 0, 'min_active_s': 0, 'min_decode_s': 0,
              'min_decode_tok_s': 0, 'min_last_half_tok_s': 0}
    identity = {'model_id': 'target120b', 'model_sha256': MODEL_SHA,
                'backend_sha': git('-C', str(BACKEND), 'rev-parse', 'HEAD'),
                'binary_sha256': sha256(binary), 'library_sha256': libs,
                'config_sha256': digest(config), 'workload_sha256': sha256(contract),
                'input_sha256': {'usage-contract.json': sha256(contract)}}
    protocol = {'schema_version': 'c2-protocol-v1', 'campaign_id': 'tesy-c9-20260927',
                'protocol_id': 'c9-8k-server-init-only-v1', 'identity': identity,
                'expected_request_ids': [], 'limits': limits,
                'c9': {'mode': 'init-only', 'model_stat': model_stat(),
                       'backend_tree': git('-C', str(BACKEND), 'rev-parse', 'HEAD^{tree}'),
                       'backend_dirty': subprocess.check_output(
                           ['git', '-C', str(BACKEND), 'status', '--porcelain'], text=True).strip(),
                       'server_runner_sha256': sha256(server.__file__),
                       'admission_runner_sha256': sha256(__file__),
                       'monitor_scope': 'systemd user scope E18, zero swap',
                       'claim': 'load/context admission only; no forward workspace or API claim'}}
    return protocol, config


def cpu_guard_violation(cpu_c, protocol):
    return (cpu_c >= protocol['limits']['cpu_max_c'] if 'c18' in protocol
            else cpu_c > 95)


def validate_receipt(protocol, config, raw, samples, root, *, run_id=RUN_ID,
                     protocol_filename='protocol.json', expected_results=0):
    if raw['stop_reasons'] or raw['returncode'] != 0 or \
       len(raw['results']) != expected_results:
        raise GateError('server load exit/result invalid')
    pre = raw['preflight']
    if pre['protocol_sha256'] != sha256(root / protocol_filename) or \
       pre['config'] != dict(config, run_id=run_id) or \
       pre['relevant_environment'] != relevant_environment(config['explicit_env']):
        raise GateError('server preflight differs from freeze')
    if pre.get('actually_loaded_backend_libraries_sha256') != protocol['identity']['library_sha256']:
        raise GateError('unexpected/missing mapped backend library')
    if pre.get('ready_elapsed_s', 121) > 120:
        raise GateError('server readiness timeout')
    launch = strict_json((root / 'raw' / f'{run_id}.launch.json').read_text())
    if launch['preflight_sha256'] != sha256(root / 'raw' / f'{run_id}.preflight.json') or \
       launch['process_identity'] != raw['launch_identity']:
        raise GateError('missing/inconsistent launch receipt')
    for suffix, expected in raw['source_sha256'].items():
        if sha256(root / 'raw' / f'{run_id}{suffix}') != expected:
            raise GateError('raw SHA mismatch: ' + suffix)
    if len(samples) < 2 or raw['sample_count'] != len(samples):
        raise GateError('endpoint telemetry absent')
    start = pre['cgroup_start']
    end = raw['cgroup_end']
    if not end or start['memory_max'] != 18 * 2**30 or start['swap_max'] != 0 or \
       end['swap_current'] != 0:
        raise GateError('cgroup cap/swap invalid')
    for key in ('events', 'events_local'):
        if any(end[key][k] != start[key][k] for k in ('max', 'oom', 'oom_kill')):
            raise GateError('cgroup cap/OOM event')
    maxima = {'rss_bytes': 0, 'cgroup_peak_bytes': 0, 'gpu_total_mib': 0,
              'cpu_c': 0, 'gpu_c': 0, 'nvme_c': 0, 'swap_bytes': 0}
    previous = None
    for sample in samples:
        t = sample['elapsed_s']
        if not isinstance(t, (int, float)) or not 0 <= t <= raw['elapsed_s'] + .25 or \
           (previous is not None and not 0 < t - previous <= 3):
            raise GateError('sample timestamp out of interval/cadence')
        previous = t
        if sample['process_identity'] != launch['process_identity'] or \
           sample['pid'] != launch['process_identity']['pid']:
            raise GateError('sample process identity changed')
        ps, cg, gpu, th = (sample[k] for k in ('proc', 'cgroup', 'gpu', 'thermal'))
        for key in ('VmRSS', 'VmSwap', 'VmHWM'):
            if type(ps.get(key)) is not int or ps[key] < 0:
                raise GateError('missing/negative process memory')
        if cg['memory_max'] != 18 * 2**30 or cg['swap_max'] != 0 or \
           cg['swap_current'] != 0 or ps['VmSwap'] != 0 or \
           any(cg[k][name] != start[k][name] for k in ('events', 'events_local')
               for name in ('max', 'oom', 'oom_kill')):
            raise GateError('sample cgroup identity/cap/swap/event invalid')
        cpu_limit_exceeded = cpu_guard_violation(th['cpu_tctl_c'], protocol)
        if ps['VmRSS'] > protocol['limits']['rss_max_bytes'] or \
           cg['memory_peak'] > protocol['limits']['memory_max_bytes'] or \
           gpu['used_mib'] > protocol['limits']['gpu_max_mib'] or \
           sample['mem_available_bytes'] < protocol['limits']['min_mem_available_bytes'] or \
           cpu_limit_exceeded or gpu['temperature_c'] > 80 or th['nvme_composite_c'] > 70:
            raise GateError('sample resource reservation/guard exceeded')
        maxima['rss_bytes'] = max(maxima['rss_bytes'], ps['VmRSS'])
        maxima['cgroup_peak_bytes'] = max(maxima['cgroup_peak_bytes'], cg['memory_peak'])
        maxima['gpu_total_mib'] = max(maxima['gpu_total_mib'], gpu['used_mib'])
        maxima['cpu_c'] = max(maxima['cpu_c'], th['cpu_tctl_c'])
        maxima['gpu_c'] = max(maxima['gpu_c'], gpu['temperature_c'])
        maxima['nvme_c'] = max(maxima['nvme_c'], th['nvme_composite_c'])
    if samples[0]['elapsed_s'] > 2 or raw['elapsed_s'] - samples[-1]['elapsed_s'] > 2:
        raise GateError('sample endpoints missing')
    return maxima


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--run', action='store_true')
    p.add_argument('--measurement-commit')
    args = p.parse_args()
    root = args.root.resolve()
    if args.freeze:
        if not root.is_dir() or not (root / 'raw').is_dir():
            p.error('no-replace campaign root/raw must already exist')
        protocol, _ = configuration(root)
        with (root / 'protocol.json').open('x') as f:
            json.dump(protocol, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
        print('frozen', root / 'protocol.json')
        return 0
    if not args.measurement_commit or git('rev-parse', 'HEAD') != args.measurement_commit or \
       git('status', '--porcelain'):
        p.error('measurement commit/worktree changed')
    protocol, config = configuration(root)
    if strict_json((root / 'protocol.json').read_text()) != protocol:
        p.error('C9 server identity/config differs from freeze')
    if program_physical_consumed() + 150 > 16 * 3600:
        p.error('program physical-time budget insufficient')
    environment()
    cool = cool_start(root, 120)
    args_c2 = SimpleNamespace(model='target120b', suite='c9init', run_id=RUN_ID,
                              protocol=root / 'protocol.json')
    returncode = server.run(args_c2, protocol, config, [], MODEL)
    raw_path = root / 'raw' / f'{RUN_ID}.json'
    raw = strict_json(raw_path.read_text())
    samples = [strict_json(line) for line in
               (root / 'raw' / f'{RUN_ID}.samples.jsonl').read_text().splitlines()]
    status = 'CAPACITY_ADMITTED_INIT_ONLY' if returncode == 0 else 'CAPACITY_NOT_ADMITTED'
    reason = None
    maxima = None
    try:
        maxima = validate_receipt(protocol, config, raw, samples, root)
        if model_stat() != protocol['c9']['model_stat']:
            raise GateError('model file identity changed')
    except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
        status = 'CAPACITY_NOT_ADMITTED'
        reason = f'{type(exc).__name__}: {exc}'
    receipt = {'schema': 'c9-server-admission-v1', 'run_id': RUN_ID,
               'measurement_commit': args.measurement_commit, 'status': status,
               'reason': reason, 'cool_start': cool, 'server_returncode': returncode,
               'load_ready_s': raw['preflight'].get('ready_elapsed_s'),
               'elapsed_s': raw['elapsed_s'], 'sample_count': len(samples),
               'maxima': maxima, 'model_stat_after': model_stat(),
               'raw_sha256': sha256(raw_path), 'protocol_sha256': sha256(root / 'protocol.json'),
               'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'claim_limit': 'init-only: forward workspace, API, prefix reuse, quality and 8K workload NOT_RUN'}
    with (root / 'admission.json').open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
    print(json.dumps({'status': status, 'reason': reason, 'maxima': maxima}, allow_nan=False))
    return 0 if status == 'CAPACITY_ADMITTED_INIT_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
