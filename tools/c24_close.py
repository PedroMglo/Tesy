#!/usr/bin/env python3
"""Close the frozen C24 input-relation failure without rewriting its raw evidence."""

import datetime as dt
import json
from pathlib import Path

from c2_gate import strict_json
from run_bounded import sha256


def write_new(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def main():
    root = Path('results/c24-session-bridge-20260927T2136Z')
    rid = 'c24-g1-prefix2048'
    receipt = strict_json((root / f'{rid}-receipt.json').read_text())
    raw_path = root / 'raw' / f'{rid}.json'
    raw = strict_json(raw_path.read_text())
    samples = [strict_json(line) for line in
               (root / 'raw' / f'{rid}.samples.jsonl').read_text().splitlines()]
    if receipt['status'] != 'FAIL_RESOURCES_OR_EVIDENCE' or \
            raw['stop_reasons'] != ['RUN_ERROR:GateError:frozen incremental token count/common prefix invalid'] or \
            raw['results'] or len(samples) < 2:
        raise RuntimeError('C24 observed state changed')
    maxima = {'cpu_c': max(s['thermal']['cpu_tctl_c'] for s in samples),
              'gpu_c': max(s['gpu']['temperature_c'] for s in samples),
              'nvme_c': max(s['thermal']['nvme_composite_c'] for s in samples),
              'gpu_total_mib': max(s['gpu']['used_mib'] for s in samples),
              'rss_bytes': max(s['proc']['VmRSS'] for s in samples),
              'cgroup_peak_bytes': max(s['cgroup']['memory_peak'] for s in samples)}
    decision = {
        'schema': 'c24-session-bridge-decision-v1',
        'status': 'FAIL_RESOURCES_OR_EVIDENCE',
        'reason': 'official tokenizer did not meet frozen +128 IDs and common-prefix relation; no request was sent',
        'failure_class': 'INPUT_FIXTURE_TOKEN_RELATION',
        'run_id': rid, 'measurement_commit': receipt['measurement_commit'],
        'raw_sha256': sha256(raw_path), 'receipt_sha256': sha256(root / f'{rid}-receipt.json'),
        'idle_status': receipt['idle']['status'], 'model_loaded': True,
        'request_count': 0, 'pair_count': 0, 'sample_count': len(samples),
        'observed_maxima_before_request': maxima,
        'swap_max_bytes': max(s['cgroup']['swap_current'] for s in samples),
        'oom_max': max(s['cgroup']['events']['oom'] for s in samples),
        'm3': 'PARTIAL_PREVIOUS_SYNTHETIC_SCOPE', 'm4': 'NOT_RUN',
        'c15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED',
        'next_action': 'new identity: observe official token counts/common prefix before freezing revised 2048+128 fixture',
        'default_changed': False,
    }
    with (root / 'runs.jsonl').open('x') as out:
        out.write(json.dumps(receipt, sort_keys=True, allow_nan=False) + '\n')
    write_new(root / 'resource-summary.json', {
        'schema':'c24-resource-summary-v1', 'run_id':rid,
        'scope':'pre-request only; no workload timing', 'maxima':maxima,
        'swap_max_bytes':decision['swap_max_bytes'], 'oom_max':decision['oom_max']})
    write_new(root / 'decision.json', decision)
    write_new(root / 'manifest.json', {
        'schema':'c24-closure-manifest-v1', 'measurement_commit':receipt['measurement_commit'],
        'protocol_sha256':sha256(root/'protocol.json'),
        'raw_sha256':sha256(raw_path),
        'receipt_sha256':sha256(root/f'{rid}-receipt.json'),
        'decision_sha256':sha256(root/'decision.json'),
        'closed_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    with (root/'LEDGER.md').open('a') as out:
        out.write(f'\n- C24 run `{rid}`: idle PASS ({receipt["idle"]["duration_s"]:.2f} s; qualifying {receipt["idle"]["qualifying_duration_s"]:.2f} s), server loaded, official token relation rejected before requests. Raw/receipt preserved; zero outputs and no M3/M4 timing claim. Max pre-request CPU/GPU/NVMe {maxima["cpu_c"]}/{maxima["gpu_c"]}/{maxima["nvme_c"]} C; swap/OOM zero. New identity required for token fixture diagnosis.\n')
    print(json.dumps({'status':decision['status'],'maxima':maxima}))


if __name__ == '__main__':
    main()
