#!/usr/bin/env python3
"""Prospective C70 full P12 OFF/ON wave-skip boundary, no timing claim."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
import c69_wave_on_boundary as prior
import c70_full_boundary_gate as gate
from c66_wave_id_diagnostic import diagnostic, BACKEND, IDS, REPO

BINARY = REPO / 'tools/c70_boundary_capture'
RUNS = {'off': 'c70-p12-wave-off01', 'on': 'c70-p12-wave-on01'}
CAP = 18 * GIB


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def frozen(root):
    p = prior.frozen(root)
    p.update(schema='c70-full-wave-boundary-v1',
        hypothesis='C57 parked CPU MMID skip preserves all 250 active numeric states and five full logits bitwise on P12 after observer repair',
        alternative='later layers/chunks or repeated captures expose arithmetic, alias or lifetime mismatch',
        claim='36-layer active-state OFF/ON comparison only; canonical layer reference, repeated ON, timing and quality separate',
        call_plan={'prefill_external_calls': 1, 'prompt_ids': 189,
                   'teacher_forced_steps': 32, 'microbatch': 32,
                   'numeric_states': 250, 'masked_states': 2},
        binary_sha256=sha256(BINARY), source_sha256=sha256(REPO / 'tools/c70_boundary_capture.cpp'),
        runner_sha256=sha256(__file__), gate_sha256=sha256(REPO / 'tools/c70_full_boundary_gate.py'),
        c7_gate_sha256=sha256(REPO / 'tools/c7_boundary_gate.py'), run_ids=RUNS)
    p.pop('run_id', None)
    p['backend_libraries_sha256'] = backend_library_hashes(str(BINARY), BACKEND)
    validate_resource_protocol(p)
    return p


def freeze(root):
    if not root.is_dir() or not (root / 'raw').is_dir():
        raise GateError('new root/raw required')
    p = frozen(root)
    save_new(root / 'protocol.json', p)
    save_new(root / 'preflight.json', {
        'schema': 'c70-preflight-v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'FROZEN_NOT_MEASURED', 'protocol_sha256': sha256(root / 'protocol.json'),
        'snapshot_sha256': sha256(root / 'snapshot.json')})


def verify(root, p, arm):
    run = RUNS[arm]
    stem = root / 'raw' / run
    manifest_path = Path(str(stem) + '.json')
    m = strict_json(manifest_path.read_text())
    capture = root / 'raw' / (run + '.capture')
    env = {'LLAMA_MOE_STREAM_NO_PRELOAD': '1'}
    if arm == 'on':
        env['TESY_CPU_WAVE_SKIP_PARKED'] = '1'
    expected = [str(BINARY), str(MODEL), str(IDS), str(capture), '--ngl', '12']
    if m['run_id'] != run or m['variant'] != f'P12-C70-wave-{arm}' or \
       m['command'] != expected or m['binary_sha256'] != p['binary_sha256'] or \
       m['backend_sha'] != p['backend_sha'] or \
       m['backend_libraries_sha256'] != p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256'] != p['backend_libraries_sha256'] or \
       not m['mapped_libraries_match_ldd'] or m['explicit_env'] != env or \
       m['artifact_identity']['stat_at_launch'] != p['model_stat'] or \
       m['artifact_identity']['stat_at_end'] != p['model_stat'] or \
       m['workload_sha256'] != p['numeric_ids_sha256'] or \
       m['resource_authority'] != p['resources'] or \
       m['limits']['resource_protocol_sha256'] != sha256(root / 'protocol.json') or \
       m['returncode'] != 0 or m['stop_reason'] is not None:
        raise GateError('C70 provenance/completion changed')
    for suffix, digest in m['output_sha256'].items():
        if sha256(Path(str(stem) + suffix)) != digest:
            raise GateError('C70 bounded raw hash changed')
    stderr = Path(str(stem) + '.stderr').read_text(errors='replace')
    placement = {int(i): dev for i, dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)', stderr)}
    if set(placement) != set(range(37)) or any(
       placement[i] != ('CPU' if i < 25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C70 placement/direct I/O changed')
    observed = gate.inspect(capture, skip_on=arm == 'on')
    return {'manifest_sha256': sha256(manifest_path),
            'coverage': observed['coverage'], 'sentinels': observed['sentinels'],
            'byte_witness_rows': observed['byte_witness_rows'],
            'maxima': m['maxima'], 'elapsed_s': m['elapsed_s']}


def run(root, commit, arm):
    os.chdir(REPO)
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    p = strict_json((root / 'protocol.json').read_text())
    pre = strict_json((root / 'preflight.json').read_text())
    if frozen(root) != p or pre['protocol_sha256'] != sha256(root / 'protocol.json') or \
       pre['snapshot_sha256'] != sha256(root / 'snapshot.json'):
        raise GateError('frozen C70 identity changed')
    if file_identity(MODEL) != p['model_stat'] or sha256(BINARY) != p['binary_sha256'] or \
       backend_library_hashes(str(BINARY), BACKEND) != p['backend_libraries_sha256']:
        raise GateError('per-arm model/binary/library changed')
    if arm == 'on' and not (root / 'raw' / (RUNS['off'] + '-receipt.json')).is_file():
        raise GateError('OFF receipt absent; ON cannot start')
    no_other_model()
    run_id = RUNS[arm]
    stem = root / 'raw' / run_id
    if Path(str(stem) + '.json').exists():
        raise GateError('no-replace run exists')
    capture = root / 'raw' / (run_id + '.capture')
    command = ['systemd-run', '--user', '--scope', '-p', f'MemoryMax={CAP}',
        '-p', 'MemorySwapMax=0', '--', 'python3', 'tools/run_bounded.py',
        '--run-id', run_id, '--model-id', 'gpt-oss-120b-mxfp4-gguf',
        '--backend', 'streaming', '--backend-root', str(BACKEND),
        '--output-root', str((root / 'raw').resolve()),
        '--variant', f'P12-C70-wave-{arm}', '--workload', str(IDS),
        '--cache-condition', 'fresh-expert-pools-page-cache-uncontrolled',
        '--timeout-s', '600', '--resource-protocol', str(root / 'protocol.json'),
        '--require-telemetry', '--ready-marker', 'C70_CONTEXT_READY',
        '--env', 'LLAMA_MOE_STREAM_NO_PRELOAD=1']
    if arm == 'on':
        command += ['--env', 'TESY_CPU_WAVE_SKIP_PARKED=1']
    command += ['--', str(BINARY), str(MODEL), str(IDS), str(capture), '--ngl', '12']
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    receipt = {'schema': 'c70-run-receipt-v1', 'run_id': run_id,
               'measurement_commit': commit, 'scope_returncode': proc.returncode,
               'scope_stderr_tail': proc.stderr[-1000:], 'status': 'FAIL_RESOURCES_OR_EVIDENCE'}
    mpath = Path(str(stem) + '.json')
    if mpath.is_file():
        m = strict_json(mpath.read_text())
        receipt.update(returncode=m.get('returncode'), stop_reason=m.get('stop_reason'),
                       maxima=m.get('maxima'), elapsed_s=m.get('elapsed_s'),
                       raw_manifest_sha256=sha256(mpath))
        receipt['invalid_id'] = diagnostic(Path(str(stem) + '.stderr').read_text(errors='replace'))
        if proc.returncode == 0:
            try:
                receipt['source'] = verify(root, p, arm)
                receipt['status'] = 'PASS_FULL_CAPTURE_SINGLE_ARM'
            except (GateError, KeyError, ValueError, TypeError, OSError) as exc:
                receipt['reason'] = f'{type(exc).__name__}: {exc}'
        elif receipt['invalid_id'] is not None:
            receipt['status'] = 'FAIL_NUMERIC_RUNTIME_ASSERTION'
            receipt['reason'] = 'invalid routed ID in full capture'
        else:
            receipt['reason'] = 'child/scope failed or resource stop'
    else:
        receipt['reason'] = 'bounded manifest absent'
    save_new(root / 'raw' / (run_id + '-receipt.json'), receipt)
    print(json.dumps({'run_id': run_id, 'status': receipt['status'],
                      'reason': receipt.get('reason')}), flush=True)
    return 0 if receipt['status'] == 'PASS_FULL_CAPTURE_SINGLE_ARM' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'run'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--measurement-commit')
    parser.add_argument('--arm', choices=tuple(RUNS))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == 'freeze':
        freeze(root)
    else:
        if not args.measurement_commit or not args.arm:
            parser.error('run needs measurement commit and arm')
        raise SystemExit(run(root, args.measurement_commit, args.arm))
