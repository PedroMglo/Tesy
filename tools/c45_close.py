#!/usr/bin/env python3
"""Close the C45 diagnostic without promoting instrumented timing."""

import json
from datetime import datetime, timezone
from pathlib import Path

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c45-wave-profile-20260928T0846Z')
INDEX = Path('results/120b-program-index.json')


def read(path):
    return strict_json(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    targets = [ROOT / name for name in ('resource-summary.json', 'decision.json', 'manifest.json')]
    if any(path.exists() for path in targets):
        raise GateError('C45 close is no-replace')
    receipt = read(ROOT / 'c45-c15-profile-cold513-receipt.json')
    raw = read(ROOT / 'raw/c45-c15-profile-cold513.json')
    nvtx = read(ROOT / 'nvtx-summary.json')
    bridge = read(ROOT / 'output-comparison.json')
    proto = read(ROOT / 'protocol.json')
    if receipt['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or raw['returncode'] != 0 or \
       raw['stop_reasons'] or bridge['status'] != 'PASS_GREEDY_FOUR_TOKEN_BRIDGE' or \
       nvtx['status'] != 'MATERIAL_UPPER_BOUND_PHASE_ATTRIBUTION_REQUIRED' or \
       receipt['protocol_sha256'] != sha256(ROOT / 'protocols/c45-c15-profile-cold513.json') or \
       receipt['measurement_commit'] != '90e5604b7a952c29c7dcb847e3ede37171ffa35a':
        raise GateError('C45 closure gates invalid')
    cg = raw['cgroup_end']
    if cg['swap_current'] or cg['swap_max'] or cg['events']['oom'] or \
       cg['events']['oom_kill'] or cg['events']['max']:
        raise GateError('C45 final cgroup failure')
    maxima = receipt['maxima']
    if maxima['cpu_c'] >= 100 or maxima['gpu_c'] >= 80 or maxima['nvme_c'] >= 70 or \
       maxima['gpu_total_mib'] >= 7000 or maxima['swap_bytes'] or \
       maxima['rss_bytes'] > 16*2**30 or maxima['cgroup_peak_bytes'] > 16.5*2**30:
        raise GateError('C45 resource guard failure')
    series = ROOT / 'raw/c45-c15-profile-cold513.samples.jsonl'
    if not series.is_file() or receipt['sample_count'] < 2:
        raise GateError('C45 telemetry absent')
    resource = {
        'schema': 'c45-resource-summary-v1', 'status': 'PASS_DIAGNOSTIC_RESOURCE_SCOPE',
        'run_id': receipt['run_id'], 'sample_count': receipt['sample_count'],
        'sample_series_sha256': sha256(series), 'maxima': maxima,
        'cpu_telemetry': receipt['cpu_telemetry'], 'cgroup_end': cg,
        'start_temperatures_c': {key: receipt['idle']['end'][key]
                                 for key in ('cpu_c', 'nvme_c')},
        'start_gpu_c': receipt['idle']['end']['gpu']['temperature_c'],
    }
    idle_total = sum(read(path)['duration_s'] for path in Path('results').glob('c*-*/**/*-idle.json'))
    physical_used = program_physical_consumed() + idle_total + 2400
    decision = {
        'schema': 'c45-decision-v1',
        'status': 'MATERIAL_UPPER_BOUND_PHASE_ATTRIBUTION_REQUIRED',
        'measurement_commit': receipt['measurement_commit'],
        'run_id': receipt['run_id'], 'greedy_four_token_bridge': bridge['status'],
        'profile_resource_status': resource['status'],
        'control_prefill_s': nvtx['control_prefill_s'],
        'plain_c15_prefill_s': read('results/c43-wave-critical-20260928T0809Z/c43-c15-plain-cold513-receipt.json')['timings']['prompt_ms']/1000,
        'profiled_c15_prefill_s_diagnostic_only': nvtx['profiled_prefill_s_diagnostic_only'],
        'mmid_union_s': nvtx['labels']['C15_CPU_STREAM_MATMUL_ID']['union_duration_s'],
        'mmid_union_over_control_prefill_percent': nvtx['mmid_union_over_control_prefill_percent'],
        'mmid_pread_overlap_s': nvtx['mmid_pread_overlap_s'],
        'bound_scope': nvtx['bound_rule'],
        'numeric_limits': nvtx['limits'],
        'causal_claim': 'NOT_ESTABLISHED',
        'wave_compaction': 'NOT_IMPLEMENTED',
        'C15_timing_promotable': False,
        'M3': 'PARTIAL', 'M4': 'NOT_RUN', 'default_changed': False,
        'old_failures_preserved': ['C43 profiler double-injection prelaunch FAIL',
                                   'C44 profiler trace environment prelaunch FAIL',
                                   'C41b high-frequency telemetry FAIL'],
        'physical_budget_consumed_s': physical_used,
        'physical_budget_remaining_s': 16*3600-physical_used,
        'next_action': 'Phase-align prefill and collect per-wave active-pair occupancy in a new diagnostic identity; bound removable exclusive MMID time before implementing compaction',
        'closed_utc': datetime.now(timezone.utc).isoformat(),
    }
    manifest = {
        'schema': 'c45-manifest-v1', 'measurement_commit': receipt['measurement_commit'],
        'run_id': receipt['run_id'], 'model_sha256': proto['model_sha256'],
        'backend_commit': proto['diagnostic_backend_commit'],
        'input_sha256': proto['input_sha256'],
        'compact_sha256': {path.name: sha256(path) for path in
                           (ROOT / 'protocol.json', ROOT / 'preflight.json',
                            ROOT / 'c45-c15-profile-cold513-receipt.json',
                            ROOT / 'output-comparison.json', ROOT / 'nvtx-summary.json')},
        'raw_sha256': {path.name: sha256(path) for path in
                       (ROOT / 'raw/c45-c15-profile-cold513.json', series,
                        ROOT / 'raw/c45-c15-profile.nsys-rep',
                        ROOT / 'raw/c45-c15-profile.sqlite')},
    }
    write_new(targets[0], resource)
    write_new(targets[1], decision)
    write_new(targets[2], manifest)
    ledger = ROOT / 'LEDGER.md'
    with ledger.open('a') as stream:
        stream.write('\n- C45 profiled run: PASS under E18; greedy four-token output matches C43 original/plain. CPU max 95.125 C warning; no guard/OOM/swap.\n')
        stream.write('- 12,300 tagged CPU MMID intervals: union 58.307 s, 73.324% of uninstrumented original control prefill 79.520 s. This is a loose upper bound across all phases, not removable or exclusive work.\n')
        stream.write('- Next: phase alignment and per-wave active-pair occupancy; C15 compaction and M4 NOT_RUN.\n')
    index = read(INDEX)
    index['units'].append({'identity': 'c45', 'root': str(ROOT), 'status': decision['status']})
    index['next_action'] = decision['next_action']
    index['updated_utc'] = decision['closed_utc']
    temp = INDEX.with_suffix('.json.tmp')
    with temp.open('x') as stream:
        json.dump(index, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    temp.replace(INDEX)
    print(json.dumps({'status': decision['status'], 'remaining_s': decision['physical_budget_remaining_s']}))


if __name__ == '__main__':
    main()
