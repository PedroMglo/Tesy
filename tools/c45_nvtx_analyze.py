#!/usr/bin/env python3
"""Bound C15 CPU MMID occupancy from the completed C45 Nsight NVTX trace."""

import json
from pathlib import Path
import sqlite3

from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path('results/c45-wave-profile-20260928T0846Z')
C43 = Path('results/c43-wave-critical-20260928T0809Z')
LABELS = ('C15_CPU_STREAM_MATMUL_ID', 'C15_EXPERT_PREAD', 'C15_EXPERT_UPLOAD')


def union_ns(intervals):
    count = 0
    low = high = None
    for start, end in sorted(intervals):
        if type(start) is not int or type(end) is not int or end <= start:
            raise GateError('NVTX interval invalid')
        if high is None:
            low, high = start, end
        elif start <= high:
            high = max(high, end)
        else:
            count += high - low
            low, high = start, end
    return count + high - low if high is not None else 0


def self_test():
    if union_ns([(0, 5), (3, 8), (11, 13)]) != 10 or \
       union_ns([(0, 5), (5, 7)]) != 7:
        raise GateError('NVTX union overlap control failed')
    try:
        union_ns([(0, 0)])
    except GateError:
        pass
    else:
        raise GateError('NVTX invalid interval mutant passed')


def main():
    self_test()
    out = ROOT / 'nvtx-summary.json'
    if out.exists():
        raise GateError('C45 NVTX no-replace output exists')
    profile = strict_json((ROOT / 'c45-c15-profile-cold513-receipt.json').read_text())
    comparison = strict_json((ROOT / 'output-comparison.json').read_text())
    control = strict_json((C43 / 'c43-control-cold513-receipt.json').read_text())
    plain = strict_json((C43 / 'c43-c15-plain-cold513-receipt.json').read_text())
    raw = strict_json((ROOT / 'raw/c45-c15-profile-cold513.json').read_text())
    if profile['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       comparison['status'] != 'PASS_GREEDY_FOUR_TOKEN_BRIDGE' or \
       control['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       plain['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       profile['message_sha256'] != control['message_sha256'] or \
       profile['message_sha256'] != plain['message_sha256'] or \
       profile['raw_sha256'] != sha256(ROOT / 'raw/c45-c15-profile-cold513.json'):
        raise GateError('C45/C43 receipt bridge invalid')
    report = ROOT / 'raw/c45-c15-profile.nsys-rep'
    db = ROOT / 'raw/c45-c15-profile.sqlite'
    if not report.is_file() or not db.is_file() or report.stat().st_size > 2*2**30:
        raise GateError('C45 Nsight raw absent/oversize')
    model_pid = raw['launch_identity']['pid']
    by_label = {}
    with sqlite3.connect(db) as conn:
        tables = {name for (name,) in conn.execute("select name from sqlite_master where type='table'")}
        if not {'NVTX_EVENTS', 'PROCESSES'} <= tables:
            raise GateError('C45 Nsight NVTX/process tables absent')
        matches = conn.execute('select globalPid,name from PROCESSES where pid=?',
                               (model_pid,)).fetchall()
        if len(matches) != 1 or matches[0][1] != 'llama-server':
            raise GateError('C45 NVTX model process identity missing/ambiguous')
        global_pid = matches[0][0]
        for label in LABELS:
            rows = conn.execute('select start,end,globalTid from NVTX_EVENTS where text=?',
                                (label,)).fetchall()
            if not rows or any(end is None or (tid & ~0xffffff) != global_pid
                               for _, end, tid in rows):
                raise GateError(f'C45 NVTX {label} absent/incomplete/wrong process')
            intervals = [(start, end) for start, end, _ in rows]
            total = sum(end - start for start, end in intervals)
            covered = union_ns(intervals)
            if not 0 < covered <= total:
                raise GateError('C45 NVTX union/sum invalid')
            by_label[label] = {'events': len(rows), 'summed_duration_s': total / 1e9,
                               'union_duration_s': covered / 1e9,
                               'span_s': (max(end for _, end in intervals) -
                                          min(start for start, _ in intervals)) / 1e9,
                               'intervals': intervals}
        combined = union_ns(sum((by_label[label]['intervals'] for label in LABELS), [])) / 1e9
        mmid_pread = union_ns(by_label[LABELS[0]]['intervals'] +
                              by_label[LABELS[1]]['intervals']) / 1e9
    control_prefill_s = control['timings']['prompt_ms'] / 1000
    if not 0 < control_prefill_s < 300:
        raise GateError('C45 original control prefill denominator invalid')
    mmid = by_label[LABELS[0]]['union_duration_s']
    pread = by_label[LABELS[1]]['union_duration_s']
    result = {
        'schema': 'c45-nvtx-occupancy-v1',
        'status': 'MATERIAL_UPPER_BOUND_PHASE_ATTRIBUTION_REQUIRED'
                  if mmid/control_prefill_s >= .20 else 'MMID_COMPACTION_DEPRIORITIZE_COLD513',
        'control_prefill_s': control_prefill_s,
        'profiled_prefill_s_diagnostic_only': profile['timings']['prompt_ms'] / 1000,
        'model_pid': model_pid,
        'nsys_global_pid': global_pid,
        'labels': {label: {k: v for k, v in values.items() if k != 'intervals'}
                   for label, values in by_label.items()},
        'mmid_union_over_control_prefill_percent': 100 * mmid / control_prefill_s,
        'pread_union_over_control_prefill_percent': 100 * pread / control_prefill_s,
        'mmid_pread_union_s': mmid_pread,
        'mmid_pread_overlap_s': mmid + pread - mmid_pread,
        'all_three_union_s': combined,
        'bound_rule': 'all tagged MMID intervals across profiled process, including decode, divided by completed uninstrumented control prefill; optimistic upper bound only',
        'limits': ['tag uses CPU MUL_MAT_ID src0 ne[2]==32; not a proved exact streaming-only marker',
                   'interval occupancy is not removable exclusive critical-path work',
                   'phase boundaries are not marked in this trace',
                   'NVTX timing cannot be promoted to production speedup',
                   'four greedy output tokens match; full logits bitwise NOT_RUN'],
        'source_sha256': {str(path): sha256(path) for path in
                          (report, db, ROOT / 'c45-c15-profile-cold513-receipt.json',
                           ROOT / 'output-comparison.json',
                           C43 / 'c43-control-cold513-receipt.json',
                           C43 / 'c43-c15-plain-cold513-receipt.json')},
        'analyzer_sha256': sha256(__file__),
    }
    with out.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'],
                      'mmid_union_percent': result['mmid_union_over_control_prefill_percent'],
                      'counts': {label: row['events'] for label, row in result['labels'].items()}},
                     allow_nan=False))


if __name__ == '__main__':
    main()
