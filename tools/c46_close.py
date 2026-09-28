#!/usr/bin/env python3
"""Close C46's bounded diagnostic and preserve its investment-only decision."""

import json
from datetime import datetime, timezone
from pathlib import Path

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256
import c46_wave_phase as campaign


ROOT = campaign.ROOT
INDEX = Path('results/120b-program-index.json')


def read(path):
    return strict_json(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    outputs = [ROOT / name for name in ('resource-summary.json', 'decision.json', 'manifest.json')]
    if any(path.exists() for path in outputs):
        raise GateError('C46 closure is no-replace')
    receipt_path = ROOT / f'{campaign.RUN_ID}-receipt.json'
    raw_path = ROOT / 'raw' / f'{campaign.RUN_ID}.json'
    samples_path = ROOT / 'raw' / f'{campaign.RUN_ID}.samples.jsonl'
    receipt = read(receipt_path)
    raw = read(raw_path)
    bridge = read(ROOT / 'output-comparison.json')
    density = read(ROOT / 'phase-density-summary.json')
    protocol = read(ROOT / 'protocol.json')
    cgroup = raw['cgroup_end']
    maxima = receipt['maxima']
    if receipt['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       raw['returncode'] != 0 or raw['stop_reasons'] or \
       bridge['status'] != 'PASS_GREEDY_FOUR_TOKEN_BRIDGE' or \
       density['status'] != 'COMPACTION_PROTOTYPE_INVESTMENT_SCREEN' or \
       receipt['measurement_commit'] != 'e122b3ea91bb4f840d666d5232aea4f2a4bb3a12' or \
       receipt['protocol_sha256'] != sha256(ROOT / 'protocols' / f'{campaign.RUN_ID}.json') or \
       receipt['raw_sha256'] != sha256(raw_path) or \
       density['analyzer_sha256'] != sha256('tools/c46_analyze.py') or \
       cgroup['swap_current'] or cgroup['swap_max'] or \
       cgroup['events']['oom'] or cgroup['events']['oom_kill'] or cgroup['events']['max'] or \
       maxima['swap_bytes'] or maxima['cpu_c'] >= 100 or maxima['gpu_c'] >= 80 or \
       maxima['nvme_c'] >= 70 or maxima['gpu_total_mib'] >= 7000 or \
       maxima['rss_bytes'] > 16*2**30 or maxima['cgroup_peak_bytes'] > 16.5*2**30 or \
       not samples_path.is_file() or receipt['sample_count'] < 2:
        raise GateError('C46 closure evidence/resource gate invalid')
    resource = {'schema': 'c46-resource-summary-v1',
                'status': 'PASS_DIAGNOSTIC_RESOURCE_SCOPE',
                'run_id': campaign.RUN_ID, 'maxima': maxima,
                'cpu_telemetry': receipt['cpu_telemetry'],
                'idle_end': receipt['idle']['end'],
                'sample_count': receipt['sample_count'],
                'sample_series_sha256': sha256(samples_path),
                'cgroup_end': cgroup}
    idle_total = sum(read(path)['duration_s'] for path in Path('results').glob('c*-*/**/*-idle.json'))
    physical_used = program_physical_consumed() + idle_total + 2400
    decision = {
        'schema': 'c46-decision-v1',
        'status': 'COMPACTION_PROTOTYPE_INVESTMENT_SCREEN',
        'measurement_commit': receipt['measurement_commit'],
        'source_commit': protocol['diagnostic_backend_commit'],
        'run_id': campaign.RUN_ID,
        'greedy_four_token_bridge': bridge['status'],
        'resource_status': resource['status'],
        'control_prefill_s': density['control_prefill_s'],
        'profiled_prefill_s_diagnostic_only': receipt['timings']['prompt_ms']/1000,
        'prefill_wave_marker_count': density['prefill_wave_marker_count'],
        'prefill_active_pairs': density['prefill_active_pairs'],
        'prefill_all_pair_slots': density['prefill_all_pair_slots'],
        'prefill_active_pair_fraction': density['prefill_active_pair_fraction'],
        'mmid_prefill_union_s': density['mmid_prefill_union_s'],
        'mmid_without_tagged_io_s': density['mmid_without_tagged_io_s'],
        'mmid_without_tagged_io_over_control_prefill_percent': density['mmid_without_tagged_io_over_control_prefill_percent'],
        'numeric_scope': 'four greedy tokens match C43; full-logit same-profile bitwise NOT_RUN',
        'causal_speedup_claim': 'NOT_ESTABLISHED',
        'compaction': 'NOT_IMPLEMENTED',
        'M3': 'PARTIAL', 'M4': 'NOT_RUN', 'default_changed': False,
        'old_failures_preserved': ['C43 profiler prelaunch FAIL', 'C44 profiler prelaunch FAIL',
                                   'C41b telemetry FAIL', 'C9-C17 CPU95 protocol thermal FAILs'],
        'physical_budget_consumed_s': physical_used,
        'physical_budget_remaining_s': 16*3600-physical_used,
        'next_action': 'C47 source/static feasibility for exact token-expert compaction with unchanged routing, then isolated prototype and canonical same-profile boundary if feasible within remaining budget',
        'closed_utc': datetime.now(timezone.utc).isoformat(),
    }
    raw_paths = (raw_path, samples_path, ROOT/'raw/c46-phase-profile.nsys-rep',
                 ROOT/'raw/c46-phase-profile.sqlite',
                 ROOT/'raw/c46-nvtx-smoke.nsys-rep', ROOT/'raw/c46-nvtx-smoke.sqlite')
    if any(not path.is_file() for path in raw_paths):
        raise GateError('C46 raw manifest incomplete')
    manifest = {
        'schema': 'c46-manifest-v1', 'measurement_commit': receipt['measurement_commit'],
        'source_commit': protocol['diagnostic_backend_commit'],
        'run_id': campaign.RUN_ID,
        'model_sha256': protocol['model_sha256'],
        'binary_sha256': receipt['binary_sha256'],
        'compact_sha256': {path.name: sha256(path) for path in
                           (ROOT/'protocol.json', ROOT/'preflight.json', receipt_path,
                            ROOT/'output-comparison.json', ROOT/'phase-density-summary.json')},
        'raw_sha256': {str(path): sha256(path) for path in raw_paths},
    }
    write_new(outputs[0], resource)
    write_new(outputs[1], decision)
    write_new(outputs[2], manifest)
    with (ROOT/'LEDGER.md').open('a') as stream:
        stream.write('\n- C46 run passed E18/CPU100 and the four-token C43 output bridge; profiled prefill 79.583 s is diagnostic. CPU max 95.125 °C warning; zero swap/OOM.\n')
        stream.write('- Prefill: 5,565 wave marks, 71,260/708,540 active pair slots (10.057%); MMID union 58.011 s, 55.594 s without tagged I/O overlap (69.911% of C43 control prefill).\n')
        stream.write('- Frozen investment screen passed. Compaction, full-logit reference and production speedup remain NOT_RUN. Next: C47 source/static feasibility and canonical boundary plan.\n')
    index = read(INDEX)
    index['units'].append({'identity': 'c46', 'root': str(ROOT), 'status': decision['status']})
    index['next_action'] = decision['next_action']
    index['updated_utc'] = decision['closed_utc']
    temp = INDEX.with_suffix('.json.tmp')
    with temp.open('x') as stream:
        json.dump(index, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    temp.replace(INDEX)
    print(json.dumps({'status': decision['status'],
                      'remaining_physical_s': decision['physical_budget_remaining_s']}))


if __name__ == '__main__':
    main()
