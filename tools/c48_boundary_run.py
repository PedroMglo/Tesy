#!/usr/bin/env python3
"""Run the frozen C48 OFF/ON/ON numeric boundary, stopping on first failure."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from c17_thermal_recovery import thermal_idle, no_other_model
from c8_observer_runner import model_stat, program_physical_consumed
from run_bounded import sha256
import c48_boundary_compare as compare


ROOT = compare.ROOT
MODEL = '/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf'
BACKEND = '/tmp/tesy-c48-backend-20260928'
IDS = 'results/c2-target-numeric-v1.ids'
BINARY = 'tools/c48_boundary_capture'


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def pair_gate():
    a, al, _ = compare.check_capture(ROOT/'raw'/f'{compare.RUNS[0]}.capture', False)
    b, bl, _ = compare.check_capture(ROOT/'raw'/f'{compare.RUNS[1]}.capture', True)
    for key, row in a.items():
        other = b[key]
        if any(row[field] != other[field] for field in ('type', 'ne', 'nb', 'bytes')) or \
           (ROOT/'raw'/f'{compare.RUNS[0]}.capture'/row['file']).read_bytes() != \
           (ROOT/'raw'/f'{compare.RUNS[1]}.capture'/other['file']).read_bytes():
            raise GateError(f'C48 first pair core mismatch {key}')
    for phase in compare.c7.LOGIT_PHASES:
        if al[phase] != bl[phase]:
            raise GateError(f'C48 first pair complete logits mismatch {phase}')
    write_new(ROOT/'pair-gate.json', {'schema':'c48-pair-gate-v1',
                                     'status':'SAME_PROFILE_BITWISE_PASS',
                                     'run_ids':list(compare.RUNS[:2]),
                                     'core_state_comparisons':len(a),
                                     'complete_logit_vectors':len(al)})


def run_arm(run_id, on, order, protocol, commit):
    if any((ROOT/'raw'/f'{run_id}{suffix}').exists() for suffix in
           ('.json','.preflight.json','.samples.jsonl','.stdout','.stderr')) or \
       (ROOT/'raw'/f'{run_id}.capture').exists():
        raise GateError('C48 no-replace arm already exists')
    if git('-C', BACKEND, 'rev-parse', 'HEAD') != protocol['backend_commit'] or \
       git('-C', BACKEND, 'status', '--porcelain') or \
       sha256(BINARY) != protocol['capture_binary_sha256'] or \
       sha256(IDS) != protocol['input_sha256'] or \
       model_stat() != protocol['model_stat']:
        raise GateError('C48 backend/binary/input/model identity differs')
    idle_total = sum(strict_json(path.read_text())['duration_s']
                     for path in Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed() + idle_total + 2400 + 900 + 600 + 90 > 16*3600:
        raise GateError('C48 physical budget cannot cover arm and cleanup')
    no_other_model()
    idle = thermal_idle(ROOT, run_id, match_tolerance_c=(5,5,3), max_start_c=(55,55,50))
    write_new(ROOT/f'{run_id}-idle.json', idle)
    if idle['status'] != 'PASS':
        write_new(ROOT/f'{run_id}-receipt.json',
                  {'run_id':run_id,'status':'THERMAL_PREFLIGHT_BLOCKED','idle':idle})
        return False
    if order == 0:
        write_new(ROOT/'baseline.json', {'cpu_c':idle['end']['cpu_c'],
                                         'gpu_c':idle['end']['gpu']['temperature_c'],
                                         'nvme_c':idle['end']['nvme_c']})
    no_other_model()
    cmd = ['systemd-run','--user','--scope','-p','MemoryMax=19327352832',
           '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
           '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
           '--backend','streaming','--backend-root',BACKEND,
           '--output-root',str((ROOT/'raw').resolve()),
           '--variant','P12-C48-skip-on' if on else 'P12-C48-skip-off',
           '--workload',IDS,'--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
           '--timeout-s','600','--max-rss-gib','16','--max-cgroup-gib','16.5',
           '--min-available-gib','6','--max-gpu-mib','6500','--max-cpu-c','100',
           '--max-gpu-c','80','--max-nvme-c','70','--require-telemetry',
           '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1']
    if on:
        cmd += ['--env','TESY_CPU_WAVE_SKIP_PARKED=1']
    cmd += ['--',BINARY,MODEL,IDS,str(ROOT/'raw'/f'{run_id}.capture'),
            '--ngl','12']
    process = subprocess.run(cmd, capture_output=True, text=True, check=False)
    manifest_path = ROOT/'raw'/f'{run_id}.json'
    receipt = {'schema':'c48-boundary-receipt-v1','run_id':run_id,
               'order':order+1,'skip_parked':on,
               'measurement_commit':commit,
               'idle':idle,'scope_returncode':process.returncode,
               'systemd_stderr_tail':process.stderr[-500:],
               'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    if manifest_path.is_file():
        manifest = strict_json(manifest_path.read_text())
        receipt.update(raw_manifest_sha256=sha256(manifest_path),
                       returncode=manifest['returncode'],
                       stop_reason=manifest['stop_reason'],
                       elapsed_s=manifest['elapsed_s'],
                       maxima=manifest['maxima'])
        if process.returncode == 0 and manifest['returncode'] == 0 and \
           manifest['stop_reason'] is None and manifest['mapped_libraries_match_ldd'] and \
           manifest['artifact_identity']['stat_at_launch'] == manifest['artifact_identity']['stat_at_end'] and \
           manifest['artifact_identity']['stat_at_launch'] == protocol['model_stat']:
            try:
                receipt['sample_count'] = resources(manifest, ROOT/'raw'/f'{run_id}.samples.jsonl')
                _, _, coverage = compare.check_capture(ROOT/'raw'/f'{run_id}.capture', on)
                receipt['coverage'] = coverage
                receipt['status'] = 'PASS_CAPTURE_SCOPE'
            except (GateError, OSError, KeyError, TypeError, ValueError) as exc:
                receipt['reason'] = f'{type(exc).__name__}: {exc}'
    write_new(ROOT/f'{run_id}-receipt.json', receipt)
    print(json.dumps({'run_id':run_id,'status':receipt['status'],
                      'elapsed_s':receipt.get('elapsed_s'),
                      'reason':receipt.get('reason')}, allow_nan=False), flush=True)
    return receipt['status'] == 'PASS_CAPTURE_SCOPE'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--measurement-commit', required=True)
    args = parser.parse_args()
    if args.root != ROOT or not (ROOT/'raw').is_dir():
        raise GateError('C48 root differs')
    protocol = strict_json((ROOT/'protocol.json').read_text())
    preflight = strict_json((ROOT/'preflight.json').read_text())
    if git('rev-parse','HEAD') != args.measurement_commit or git('status','--porcelain') or \
       protocol['runner_sha256'] != sha256(__file__) or \
       preflight['guard_status'] != 'READY_FOR_IDLE_ADMISSION' or \
       preflight['power_source'] != 'AC' or \
       subprocess.check_output(['powerprofilesctl','get'],text=True).strip() != preflight['power_profile'] or \
       Path('/sys/class/power_supply/AC0/online').read_text().strip() != '1':
        raise GateError('C48 frozen commit/preflight/power differs')
    for i, (run_id, on) in enumerate(zip(compare.RUNS,(False,True,True))):
        if not run_arm(run_id, on, i, protocol, args.measurement_commit):
            return 1
        if i == 1:
            try:
                pair_gate()
            except (GateError, OSError, KeyError, TypeError, ValueError) as exc:
                write_new(ROOT/'pair-gate.json', {'schema':'c48-pair-gate-v1',
                                                  'status':'FAIL_SAME_PROFILE_FIDELITY',
                                                  'reason':f'{type(exc).__name__}: {exc}',
                                                  'run_ids':list(compare.RUNS[:2])})
                return 1
    try:
        compare.main()
    except (GateError, OSError, KeyError, TypeError, ValueError) as exc:
        write_new(ROOT/'boundary-summary.json', {'schema':'c48-boundary-summary-v1',
                                                  'status':'FAIL_SAME_PROFILE_FIDELITY',
                                                  'reason':f'{type(exc).__name__}: {exc}',
                                                  'run_ids':list(compare.RUNS)})
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
