#!/usr/bin/env python3
"""Freeze one C46 model diagnostic after source build and model-free NVTX smoke."""

import json
from pathlib import Path
import sqlite3
import subprocess

from c2_gate import GateError, strict_json
from run_bounded import backend_library_hashes, sha256
import c18_cpu_telemetry as telemetry
import c46_wave_phase as runner


ROOT = runner.ROOT
C45 = runner.C45
BACKEND = runner.BACKEND
BINARY = BACKEND / 'build-c33-nvtx/bin/llama-server'
SOURCE_COMMIT = '005e8ff'
SMOKE = Path('/tmp/c46-nvtx-smoke.sqlite')


def git(*args):
    return subprocess.check_output(['git', '-C', str(BACKEND), *args], text=True).strip()


def write_new(path, row):
    with path.open('x') as stream:
        json.dump(row, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    top_path = ROOT / 'protocol.json'
    test_path = ROOT / 'model-free-tests.json'
    if top_path.exists() or test_path.exists():
        raise GateError('C46 preparation is no-replace')
    if not git('rev-parse', 'HEAD').startswith(SOURCE_COMMIT) or git('status', '--porcelain'):
        raise GateError('C46 source not pinned/clean')
    if not BINARY.is_file() or not SMOKE.is_file():
        raise GateError('C46 server/smoke absent')
    help_run = subprocess.run([str(BINARY), '--help'], stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, text=True, timeout=15)
    if help_run.returncode != 0:
        raise GateError('C46 server model-free help failed')
    with sqlite3.connect(SMOKE) as db:
        events = db.execute("select eventType,text,end from NVTX_EVENTS where text like 'C46_%' order by start").fetchall()
    if len(events) != 2 or events[0][0] != 59 or events[0][1] != 'C46_SERVER_PREFILL_DECODE' or \
       events[0][2] is None or events[1] != (34, 'C46_WAVE_LAYER=0_WAVE=0_ACTIVE=1_OF=32', None):
        raise GateError('C46 NVTX phase/mark model-free smoke failed')
    c45 = strict_json((C45 / 'protocol.json').read_text())
    c45['schema'] = 'c46-wave-phase-protocol-v1'
    c45['status'] = 'FROZEN_BEFORE_C46_MODEL'
    c45['objective'] = 'phase-align CPU streamed MMID and count active token-expert pairs per wave in one diagnostic cold513 request'
    c45['hypothesis'] = 'material prefill MMID occupancy includes sparse inactive parked pairs that a compact execution might avoid'
    c45['alternative'] = 'tagged MMID mainly executes active work or overlaps other critical work; pair density alone cannot imply latency saving'
    c45['bound_rule'] = 'intersect tagged MMID intervals with server prefill decode ranges, then subtract overlap with tagged pread/upload; report per-wave active/all pairs separately; no speedup estimate without exclusive removable cost'
    c45['parent_c45_decision_sha256'] = sha256(C45 / 'decision.json')
    c45['diagnostic_backend_commit'] = git('rev-parse', 'HEAD')
    c45['diagnostic_server_sha256'] = sha256(BINARY)
    c45['diagnostic_source_sha256'] = {str(path): sha256(path) for path in
                                       (BACKEND / 'src/llama-moe-stream.cpp',
                                        BACKEND / 'tools/server/server-context.cpp')}
    c45['runner_sha256'] = sha256(runner.__file__)
    c45['cpu_telemetry_sha256'] = sha256(telemetry.__file__)
    c45['input_sha256'] = sha256(ROOT / 'input.json')
    c45['usage_contract_sha256'] = sha256(ROOT / 'usage-contract.json')
    c45['reference_message_sha256'] = runner.reference()['message_sha256']
    c45['phase_marker_contract'] = {
        'prefill': 'C46_SERVER_PREFILL_DECODE around llama_decode while slot PROCESSING_PROMPT or DONE_PROMPT',
        'generation': 'C46_SERVER_GENERATION_DECODE after slot state GENERATING',
        'wave': 'C46_WAVE_LAYER=il_WAVE=w_ACTIVE=a_OF=n instant marker after stage/emit',
        'one_slot_only': True,
        'minimum_prefill_ranges': 1,
        'minimum_wave_markers': 1,
        'minimum_mmid_ranges': 1,
        'numeric_scope': 'four greedy output tokens equal C43 original and C15 plain; full logits bitwise NOT_RUN',
    }
    c45['decision_rule'] = 'investment screen only: if active/all prefill wave pairs <=0.75 and prefill MMID time without tagged pread/upload >=20% of C43 original prefill, consider scoped compaction with prospective canonical reference and budget; otherwise pivot to prefix/session/residency; no timing promotion from profiler'
    c45['investment_screen'] = {'max_active_pair_fraction': 0.75,
                                'min_mmid_without_tagged_io_over_control_prefill': 0.20,
                                'interpretation': 'both are diagnostic necessary conditions for prototype investment, neither predicts speedup'}
    c45['order'] = [runner.RUN_ID]
    c45['profiler_command'] = f'systemd-run --user --scope E18 -- env -u LD_PRELOAD PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools nsys profile --trace=nvtx --sample=none --force-overwrite=false --output {ROOT}/raw/c46-phase-profile -- python3 tools/c46_wave_phase.py {ROOT} --run --measurement-commit <freeze-commit>'
    c45['default_changed'] = False
    libraries = backend_library_hashes(str(BINARY), BACKEND)
    if not libraries:
        raise GateError('C46 backend library hashes absent')
    tests = {
        'schema': 'c46-model-free-tests-v1', 'status': 'PASS',
        'source_commit': c45['diagnostic_backend_commit'],
        'source_clean': True,
        'build_flags': strict_json(Path('results/c33-wave-tracer-feasibility-20260928T0034Z/protocol.json').read_text())['build_flags'],
        'binary_sha256': c45['diagnostic_server_sha256'],
        'library_sha256': libraries,
        'help_exit_code': help_run.returncode,
        'smoke_events': [{'event_type': kind, 'text': label} for kind, label, _ in events],
        'smoke_sqlite_sha256': sha256(SMOKE),
        'smoke_report_sha256': sha256('/tmp/c46-nvtx-smoke.nsys-rep'),
        'limits': ['smoke is model-free; actual phase and wave marker coverage remains unmeasured',
                   'diagnostic backend only; no full-logit fidelity claim'],
    }
    write_new(top_path, c45)
    write_new(test_path, tests)
    print(json.dumps({'status': 'FROZEN_TOP', 'backend_commit': c45['diagnostic_backend_commit'],
                      'binary_sha256': c45['diagnostic_server_sha256']}))


if __name__ == '__main__':
    main()
