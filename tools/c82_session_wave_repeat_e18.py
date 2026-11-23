#!/usr/bin/env python3
"""One E18 C75 session-port ON repeat after the C78 E16 resource stop."""
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
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
import c76_session_wave_boundary as parent
import c72_wave_repeat_gate as gate
from c66_wave_id_diagnostic import diagnostic, IDS, REPO

SOURCE_ROOT = REPO / 'results/c76b-session-wave-boundary-20260928T1918Z'
FIRST = SOURCE_ROOT / 'raw/c76b-p12-session-wave-on01.capture'
BACKEND = parent.BACKEND
BINARY = parent.BINARY
RUN = 'c82-p12-session-wave-on-repeat01'
CAP = 18 * GIB


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def frozen(root):
    p = strict_json((SOURCE_ROOT/'protocol.json').read_text())
    manifest = strict_json((SOURCE_ROOT / 'manifest.json').read_text())
    for path, record in manifest['raw_sha256'].items():
        if path.startswith('raw/c76b-p12-session-wave-on01.capture/'):
            file = SOURCE_ROOT / path
            if file.stat().st_size != record['bytes'] or sha256(file) != record['sha256']:
                raise GateError('C76b first ON raw hash changed')
    snapshot = strict_json((root/'snapshot.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot) != policy or \
       file_identity(MODEL) != p['model_stat'] or \
       any(snapshot['model_stat'][k] != p['model_stat'][k]
           for k in ('dev','inode','size_bytes','mtime_ns')) or \
       git('-C',BACKEND,'rev-parse','HEAD') != parent.BACKEND_SHA or \
       git('-C',BACKEND,'status','--porcelain') or \
       sha256(BINARY) != p['binary_sha256'] or \
       backend_library_hashes(str(BINARY), BACKEND) != p['backend_libraries_sha256']:
        raise GateError('C82 resource snapshot changed')
    p.update(schema='c82-session-wave-on-repeat-e18-v1', campaign_id=root.name, run_id=RUN,
        hypothesis='C75 session-port wave ON preserves full P12 active boundary and logits across a fresh process',
        alternative='capture or async scheduler race causes nondeterminism, or file charge still exceeds E18 preventive margin',
        claim='one fresh-process ON repetition against C76b ON; no session timing or quality',
        runner_sha256=sha256(__file__),
        repeat_gate_sha256=sha256(REPO / 'tools/c72_wave_repeat_gate.py'),
        C76b_manifest_sha256=sha256(SOURCE_ROOT / 'manifest.json'),
        C76b_first_index_sha256=sha256(FIRST / 'index.tsv'),
        resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP),
        resource_note='E18 fresh admission addresses the measured C78 E16 preventive stop; no timing comparison')
    p.pop('run_ids', None)
    validate_resource_protocol(p)
    return p


def freeze(root):
    if not root.is_dir() or not (root / 'raw').is_dir():
        raise GateError('new root/raw required')
    p = frozen(root)
    save_new(root / 'protocol.json', p)
    save_new(root / 'preflight.json', {
        'schema': 'c82-preflight-v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'FROZEN_NOT_MEASURED', 'protocol_sha256': sha256(root / 'protocol.json'),
        'snapshot_sha256': sha256(root / 'snapshot.json')})


def verify(root, p):
    stem = root / 'raw' / RUN
    manifest_path = Path(str(stem) + '.json')
    m = strict_json(manifest_path.read_text())
    capture = root / 'raw' / (RUN + '.capture')
    env = {'LLAMA_MOE_STREAM_NO_PRELOAD': '1', 'TESY_CPU_WAVE_SKIP_PARKED': '1'}
    expected = [str(BINARY), str(MODEL), str(IDS), str(capture), '--ngl', '12']
    if m['run_id'] != RUN or m['variant'] != 'P12-C82-session-wave-on-repeat' or \
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
        raise GateError('C82 provenance/completion changed')
    for suffix, digest in m['output_sha256'].items():
        if sha256(Path(str(stem) + suffix)) != digest:
            raise GateError('C82 bounded raw hash changed')
    stderr = Path(str(stem) + '.stderr').read_text(errors='replace')
    placement = {int(i): dev for i, dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)', stderr)}
    if set(placement) != set(range(37)) or any(
       placement[i] != ('CPU' if i < 25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C82 placement/direct I/O changed')
    comparison = gate.compare(FIRST, capture)
    return {'manifest_sha256': sha256(manifest_path), 'comparison': comparison,
            'maxima': m['maxima'], 'elapsed_s': m['elapsed_s']}


def run(root, commit):
    os.chdir(REPO)
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement commit/tree/environment changed')
    p = strict_json((root / 'protocol.json').read_text())
    pre = strict_json((root / 'preflight.json').read_text())
    if frozen(root) != p or pre['protocol_sha256'] != sha256(root / 'protocol.json') or \
       pre['snapshot_sha256'] != sha256(root / 'snapshot.json'):
        raise GateError('frozen C82 identity changed')
    if file_identity(MODEL) != p['model_stat'] or sha256(BINARY) != p['binary_sha256'] or \
       backend_library_hashes(str(BINARY), BACKEND) != p['backend_libraries_sha256']:
        raise GateError('per-arm model/binary/library changed')
    no_other_model()
    stem = root / 'raw' / RUN
    if Path(str(stem) + '.json').exists():
        raise GateError('no-replace run exists')
    capture = root / 'raw' / (RUN + '.capture')
    command = ['systemd-run', '--user', '--scope', '-p', f'MemoryMax={CAP}',
        '-p', 'MemorySwapMax=0', '--', 'python3', 'tools/run_bounded.py',
        '--run-id', RUN, '--model-id', 'gpt-oss-120b-mxfp4-gguf',
        '--backend', 'streaming', '--backend-root', str(BACKEND),
        '--output-root', str((root / 'raw').resolve()),
        '--variant', 'P12-C82-session-wave-on-repeat', '--workload', str(IDS),
        '--cache-condition', 'fresh-expert-pools-page-cache-uncontrolled',
        '--timeout-s', '600', '--resource-protocol', str(root / 'protocol.json'),
        '--require-telemetry', '--ready-marker', 'C70_CONTEXT_READY',
        '--env', 'LLAMA_MOE_STREAM_NO_PRELOAD=1',
        '--env', 'TESY_CPU_WAVE_SKIP_PARKED=1', '--',
        str(BINARY), str(MODEL), str(IDS), str(capture), '--ngl', '12']
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    receipt = {'schema': 'c82-run-receipt-v1', 'run_id': RUN,
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
                receipt['source'] = verify(root, p)
                receipt['status'] = receipt['source']['comparison']['status']
            except (GateError, KeyError, ValueError, TypeError, OSError) as exc:
                receipt['reason'] = f'{type(exc).__name__}: {exc}'
        elif receipt['invalid_id'] is not None:
            receipt['status'] = 'FAIL_NUMERIC_RUNTIME_ASSERTION'
            receipt['reason'] = 'invalid routed ID in repeat'
        else:
            receipt['reason'] = 'child/scope failed or resource stop'
    else:
        receipt['reason'] = 'bounded manifest absent'
    save_new(root / 'raw' / (RUN + '-receipt.json'), receipt)
    save_new(root / 'boundary-summary.json', receipt)
    print(json.dumps({'run_id': RUN, 'status': receipt['status'],
                      'mismatch': receipt.get('source', {}).get('comparison', {}).get('mismatch'),
                      'reason': receipt.get('reason')}), flush=True)
    return 0 if receipt['status'] == 'SAME_PROFILE_BITWISE_PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'run'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--measurement-commit')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == 'freeze':
        freeze(root)
    else:
        if not args.measurement_commit:
            parser.error('run needs measurement commit')
        raise SystemExit(run(root, args.measurement_commit))
