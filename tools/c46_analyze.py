#!/usr/bin/env python3
"""Intersect C46 NVTX work with prefill ranges and count active wave pairs."""

import json
from pathlib import Path
import re
import sqlite3

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c46_wave_phase as campaign


ROOT = campaign.ROOT
C43 = campaign.C43
RANGE_LABELS = ('C46_SERVER_PREFILL_DECODE', 'C46_SERVER_GENERATION_DECODE',
                'C15_CPU_STREAM_MATMUL_ID', 'C15_EXPERT_PREAD', 'C15_EXPERT_UPLOAD')
MARKER = re.compile(r'C46_WAVE_LAYER=(\d+)_WAVE=(\d+)_ACTIVE=(\d+)_OF=(\d+)')


def merge(intervals):
    out = []
    for start, end in sorted(intervals):
        if type(start) is not int or type(end) is not int or end <= start:
            raise GateError('C46 invalid NVTX interval')
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def intersect(left, right):
    a, b = merge(left), merge(right)
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            out.append((start, end))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return out


def duration_ns(intervals):
    return sum(end-start for start, end in merge(intervals))


def tests():
    if merge([(0, 5), (3, 8), (11, 13)]) != [(0, 8), (11, 13)] or \
       intersect([(0, 8), (11, 13)], [(4, 12)]) != [(4, 8), (11, 12)] or \
       duration_ns(intersect([(0, 8), (11, 13)], [(4, 12)])) != 5:
        raise GateError('C46 interval positive control failed')
    for mutant in ([(0, 0)], [(5, 4)], [(0.0, 1)]):
        try:
            merge(mutant)
        except GateError:
            continue
        raise GateError('C46 interval negative control passed')
    if MARKER.fullmatch('C46_WAVE_LAYER=25_WAVE=2_ACTIVE=13_OF=128') is None or \
       MARKER.fullmatch('C46_WAVE_LAYER=x_WAVE=2_ACTIVE=13_OF=128') is not None:
        raise GateError('C46 marker parser controls failed')


def main():
    tests()
    out = ROOT / 'phase-density-summary.json'
    if out.exists():
        raise GateError('C46 analyzer is no-replace')
    receipt_path = ROOT / f'{campaign.RUN_ID}-receipt.json'
    receipt = strict_json(receipt_path.read_text())
    raw_path = ROOT / 'raw' / f'{campaign.RUN_ID}.json'
    raw = strict_json(raw_path.read_text())
    bridge = strict_json((ROOT / 'output-comparison.json').read_text())
    top = strict_json((ROOT / 'protocol.json').read_text())
    control = strict_json((C43 / 'c43-control-cold513-receipt.json').read_text())
    if receipt['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       bridge['status'] != 'PASS_GREEDY_FOUR_TOKEN_BRIDGE' or \
       receipt['message_sha256'] != control['message_sha256'] or \
       receipt['raw_sha256'] != sha256(raw_path) or \
       receipt['protocol_sha256'] != sha256(ROOT / 'protocols' / f'{campaign.RUN_ID}.json') or \
       raw['returncode'] != 0 or raw['stop_reasons'] or \
       top['phase_marker_contract']['one_slot_only'] is not True or \
       receipt['token_ids_sha256'] != top['official_prompt_ids_sha256']:
        raise GateError('C46 raw/receipt/frozen bridge invalid')
    report = ROOT / 'raw/c46-phase-profile.nsys-rep'
    db_path = ROOT / 'raw/c46-phase-profile.sqlite'
    if not report.is_file() or not db_path.is_file() or report.stat().st_size > 2*2**30:
        raise GateError('C46 profiler raw absent/oversize')
    model_pid = raw['launch_identity']['pid']
    by_label = {}
    with sqlite3.connect(db_path) as db:
        tables = {name for (name,) in db.execute("select name from sqlite_master where type='table'")}
        if not {'PROCESSES', 'NVTX_EVENTS'} <= tables:
            raise GateError('C46 profiler process/NVTX table absent')
        rows = db.execute('select globalPid,name from PROCESSES where pid=?', (model_pid,)).fetchall()
        if len(rows) != 1 or rows[0][1] != 'llama-server':
            raise GateError('C46 model PID ambiguous')
        global_pid = rows[0][0]
        for label in RANGE_LABELS:
            rows = db.execute('select start,end,eventType,globalTid from NVTX_EVENTS where text=?',
                              (label,)).fetchall()
            if not rows or any(kind != 59 or end is None or (tid & ~0xffffff) != global_pid
                               for _, end, kind, tid in rows):
                raise GateError(f'C46 NVTX range absent/invalid: {label}')
            by_label[label] = [(start, end) for start, end, _, _ in rows]
        marker_rows = db.execute("select start,end,eventType,text,globalTid from NVTX_EVENTS where text like 'C46_WAVE_%'").fetchall()
    prefill = merge(by_label[RANGE_LABELS[0]])
    generation = merge(by_label[RANGE_LABELS[1]])
    if intersect(prefill, generation):
        raise GateError('C46 prefill/generation range overlap')
    waves = []
    for start, end, kind, label, tid in marker_rows:
        match = MARKER.fullmatch(label or '')
        if kind != 34 or end is not None or (tid & ~0xffffff) != global_pid or not match:
            raise GateError('C46 wave mark invalid')
        layer, wave, active, total = map(int, match.groups())
        if layer > 35 or wave > 255 or total == 0 or active > total:
            raise GateError('C46 wave mark values invalid')
        phase = 'prefill' if any(a <= start <= b for a, b in prefill) else \
                'generation' if any(a <= start <= b for a, b in generation) else 'outside'
        if phase == 'outside':
            raise GateError('C46 wave marker outside decode ranges')
        waves.append({'layer': layer, 'wave': wave, 'active': active,
                      'all': total, 'phase': phase, 'global_tid': tid})
    prefill_waves = [row for row in waves if row['phase'] == 'prefill']
    if len(prefill) < top['phase_marker_contract']['minimum_prefill_ranges'] or \
       len(prefill_waves) < top['phase_marker_contract']['minimum_wave_markers'] or \
       len(by_label['C15_CPU_STREAM_MATMUL_ID']) < top['phase_marker_contract']['minimum_mmid_ranges']:
        raise GateError('C46 frozen marker coverage incomplete')
    all_pairs = sum(row['all'] for row in prefill_waves)
    active_pairs = sum(row['active'] for row in prefill_waves)
    mmid_prefill = intersect(by_label['C15_CPU_STREAM_MATMUL_ID'], prefill)
    io_prefill = intersect(by_label['C15_EXPERT_PREAD'] + by_label['C15_EXPERT_UPLOAD'], prefill)
    mmid_io_overlap = intersect(mmid_prefill, io_prefill)
    mmid_s = duration_ns(mmid_prefill)/1e9
    mmid_without_io_s = mmid_s - duration_ns(mmid_io_overlap)/1e9
    control_prefill_s = control['timings']['prompt_ms']/1000
    if not 0 < mmid_without_io_s <= mmid_s <= duration_ns(prefill)/1e9 or \
       not 0 < control_prefill_s < 300 or not 0 <= active_pairs <= all_pairs:
        raise GateError('C46 phase/bound arithmetic invalid')
    active_fraction = active_pairs/all_pairs
    without_io_fraction = mmid_without_io_s/control_prefill_s
    screen = top['investment_screen']
    outcome = 'COMPACTION_PROTOTYPE_INVESTMENT_SCREEN' if \
              active_fraction <= screen['max_active_pair_fraction'] and \
              without_io_fraction >= screen['min_mmid_without_tagged_io_over_control_prefill'] else \
              'COMPACTION_DEPRIORITIZE_COLD513'
    result = {
        'schema': 'c46-phase-density-summary-v1', 'status': outcome,
        'model_pid': model_pid, 'nsys_global_pid': global_pid,
        'prefill_decode_range_count': len(by_label[RANGE_LABELS[0]]),
        'generation_decode_range_count': len(by_label[RANGE_LABELS[1]]),
        'prefill_decode_union_s': duration_ns(prefill)/1e9,
        'generation_decode_union_s': duration_ns(generation)/1e9,
        'mmid_prefill_interval_count': len(by_label['C15_CPU_STREAM_MATMUL_ID']),
        'mmid_prefill_union_s': mmid_s,
        'tagged_io_prefill_union_s': duration_ns(io_prefill)/1e9,
        'mmid_tagged_io_overlap_s': duration_ns(mmid_io_overlap)/1e9,
        'mmid_without_tagged_io_s': mmid_without_io_s,
        'mmid_without_tagged_io_over_control_prefill_percent': 100*without_io_fraction,
        'control_prefill_s': control_prefill_s,
        'prefill_wave_marker_count': len(prefill_waves),
        'generation_wave_marker_count': len(waves)-len(prefill_waves),
        'prefill_active_pairs': active_pairs, 'prefill_all_pair_slots': all_pairs,
        'prefill_active_pair_fraction': active_fraction,
        'prefill_zero_active_wave_count': sum(row['active']==0 for row in prefill_waves),
        'prefill_waves_by_layer': {str(il): {'wave_marks': sum(row['layer']==il for row in prefill_waves),
                                             'active_pairs': sum(row['active'] for row in prefill_waves if row['layer']==il),
                                             'all_pair_slots': sum(row['all'] for row in prefill_waves if row['layer']==il)}
                                   for il in sorted({row['layer'] for row in prefill_waves})},
        'investment_screen': screen,
        'limits': ['MMID tag specificity to streamed expert work remains source-inferred',
                   'no direct pairing of each wave mark with every MMID operation is claimed',
                   'absence of overlap with tagged I/O is not proof of removable exclusive critical-path work',
                   'active pair fraction is not expected speedup; compaction overhead and arithmetic changes unmeasured',
                   'profiled timing is diagnostic; no production speedup or full-logit fidelity claim'],
        'source_sha256': {str(path): sha256(path) for path in
                          (report, db_path, receipt_path, ROOT/'output-comparison.json',
                           ROOT/'protocol.json', C43/'c43-control-cold513-receipt.json')},
        'analyzer_sha256': sha256(__file__),
    }
    with out.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': outcome,
                      'active_fraction': active_fraction,
                      'mmid_without_io_percent': 100*without_io_fraction}))


if __name__ == '__main__':
    main()
