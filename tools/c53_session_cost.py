#!/usr/bin/env python3
"""Model-free /proc I/O accounting across C52b request phases."""

import argparse
import json
import math
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path('results/c53-session-cost-20260928T1255Z')
PARENT = Path('results/c52b-assistant-history-sustained-20260928T1132Z')
RUN_ID = 'c52b-p12-assistant-history01'
GIB = 2**30


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def at(samples, t, key):
    """Interpolate one monotone cumulative process counter at a phase boundary."""
    if not samples or not samples[0]['elapsed_s'] <= t <= samples[-1]['elapsed_s']:
        raise GateError('phase boundary outside sampled process lifetime')
    for left, right in zip(samples, samples[1:]):
        a, b = left['elapsed_s'], right['elapsed_s']
        if not (math.isfinite(a) and math.isfinite(b) and 0 < b-a <= 3):
            raise GateError('invalid sample cadence')
        va, vb = left['proc'].get(key), right['proc'].get(key)
        if type(va) is not int or type(vb) is not int or va < 0 or vb < va:
            raise GateError('nonmonotone or missing process I/O counter')
        if a <= t <= b:
            return va + (vb-va)*(t-a)/(b-a)
    if t == samples[-1]['elapsed_s']:
        value = samples[-1]['proc'].get(key)
        if type(value) is int and value >= 0:
            return float(value)
    raise GateError('phase boundary not bracketed')


def analyze(raw, samples):
    if raw['stop_reasons'] or raw['returncode'] != 0 or len(raw['results']) != 20:
        raise GateError('C52b parent run incomplete')
    rows = []
    for index, result in enumerate(raw['results']):
        start, end = result['started_s'], result['ended_s']
        prefill_s = result['timings']['prompt_ms']/1000
        decode_s = result['timings']['predicted_ms']/1000
        boundary = start + prefill_s
        if not (0 < prefill_s < end-start and 0 < decode_s < end-start and
                abs((prefill_s+decode_s)-(end-start)) < 1):
            raise GateError('server phase timer inconsistent with request receipt')
        counters = {}
        for key in ('read_bytes','rchar','syscr'):
            beginning, middle, ending = (at(samples, instant, key)
                                          for instant in (start,boundary,end))
            counters[key] = {'prefill':middle-beginning,
                             'decode':ending-middle,
                             'request':ending-beginning}
        rows.append({'index':index,'request_id':result['id'],
                     'prompt_ids':result['usage']['prompt_tokens'],
                     'cached_ids':result['timings']['cache_n'],
                     'prefill_s':prefill_s,'decode_s':decode_s,
                     'request_wall_s':end-start,
                     'read_bytes':counters['read_bytes'],
                     'rchar':counters['rchar'],'syscr':counters['syscr']})
    inc = rows[1:]
    summary = {'schema':'c53-session-io-accounting-v1',
               'evidence_class':'DIAGNOSTIC_PROC_IO_ACCOUNTING',
               'parent_run_id':RUN_ID,'request_count':len(rows),
               'incremental_request_count':len(inc),
               'incremental_prompt_new_ids':sorted(set(x['prompt_ids']-x['cached_ids'] for x in inc)),
               'incremental_prefill_median_s':median(x['prefill_s'] for x in inc),
               'incremental_decode_median_s':median(x['decode_s'] for x in inc),
               'incremental_prefill_read_bytes_median':median(x['read_bytes']['prefill'] for x in inc),
               'incremental_decode_read_bytes_median':median(x['read_bytes']['decode'] for x in inc),
               'incremental_request_read_bytes_median':median(x['read_bytes']['request'] for x in inc),
               'incremental_prefill_read_rate_median_gib_s':median(x['read_bytes']['prefill']/GIB/x['prefill_s'] for x in inc),
               'incremental_decode_read_rate_median_gib_s':median(x['read_bytes']['decode']/GIB/x['decode_s'] for x in inc),
               'rows':rows,
               'limits':['/proc/PID/io read_bytes and rchar are process accounting, not independent physical NVMe counters',
                         'linear interpolation at <=3 s samples is diagnostic',
                         'phase boundary approximated by request start plus server prompt_ms',
                         'accounted bytes do not identify experts, destinations, overlap or exclusive critical-path wait',
                         'C46 cold513 wave intervals are a different workload and cannot be applied numerically to this warm 153-ID session']}
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.root != ROOT or not ROOT.is_dir():
        raise GateError('C53 root differs')
    protocol = strict_json((ROOT/'protocol.json').read_text())
    if protocol['schema'] != 'c53-session-cost-protocol-v1' or \
       protocol['analyzer_sha256'] != sha256(__file__) or \
       protocol['source_c46_phase_summary_sha256'] != sha256(
           'results/c46-wave-phase-20260928T0857Z/phase-density-summary.json'):
        raise GateError('C53 model-free source/protocol differs from freeze')
    parent_manifest = strict_json((PARENT/'manifest.json').read_text())
    parent_decision = strict_json((PARENT/'decision.json').read_text())
    if protocol['input_sha256'] != {
        'decision':sha256(PARENT/'decision.json'),
        'manifest':sha256(PARENT/'manifest.json'),
        'raw':sha256(PARENT/'raw'/(RUN_ID+'.json')),
        'samples':sha256(PARENT/'raw'/(RUN_ID+'.samples.jsonl'))}:
        raise GateError('C53 parent evidence differs from freeze')
    if parent_decision['specific_result'] != 'PASS_SUSTAINED_ASSISTANT_HISTORY_TESTED_SCOPE':
        raise GateError('C52b parent status invalid')
    names = (RUN_ID+'.json',RUN_ID+'.samples.jsonl')
    for name in names:
        if sha256(PARENT/'raw'/name) != parent_manifest['raw_sha256'][name]['sha256']:
            raise GateError('C52b raw SHA differs from manifest')
    raw = strict_json((PARENT/'raw'/names[0]).read_text())
    samples = [strict_json(line) for line in (PARENT/'raw'/names[1]).read_text().splitlines()]
    summary = analyze(raw,samples)
    summary['parent_decision_sha256'] = sha256(PARENT/'decision.json')
    summary['parent_manifest_sha256'] = sha256(PARENT/'manifest.json')
    summary['parent_raw_sha256'] = {name:sha256(PARENT/'raw'/name) for name in names}
    write_new(ROOT/'io-accounting.json',summary)
    print(json.dumps({'status':summary['evidence_class'],
                      'request_count':summary['request_count'],
                      'median_incremental_read_gib':summary['incremental_request_read_bytes_median']/GIB},allow_nan=False))


if __name__ == '__main__':
    raise SystemExit(main())
