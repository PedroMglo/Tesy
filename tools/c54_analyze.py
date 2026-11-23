#!/usr/bin/env python3
"""Attribute NVTX interval coverage to the second, warm-prefix C54 request."""

import json
from pathlib import Path
import re
import sqlite3

from c2_gate import GateError, strict_json
from c46_analyze import merge, intersect, duration_ns
from run_bounded import sha256
import c54_warm_phase as campaign


ROOT = campaign.ROOT
LABELS = ('C46_SERVER_PREFILL_DECODE', 'C46_SERVER_GENERATION_DECODE',
          'C15_CPU_STREAM_MATMUL_ID', 'C15_EXPERT_PREAD', 'C15_EXPERT_UPLOAD')
MARKER = re.compile(r'C46_WAVE_LAYER=(\d+)_WAVE=(\d+)_ACTIVE=(\d+)_OF=(\d+)')


def request_groups(ranges, split_gap_ns=120_000_000_000):
    rows = sorted(ranges)
    if not rows:
        raise GateError('C54 prefill ranges missing')
    groups = [[rows[0]]]
    for row in rows[1:]:
        if row[0] - groups[-1][-1][1] > split_gap_ns:
            groups.append([])
        groups[-1].append(row)
    if len(groups) != 2 or any(not group for group in groups):
        raise GateError('C54 expected exactly two separated request prefills')
    return groups


def test():
    if request_groups([(0, 10), (11, 20), (120_000_000_021, 120_000_000_031)]) != \
       [[(0, 10), (11, 20)], [(120_000_000_021, 120_000_000_031)]]:
        raise GateError('C54 request segmentation positive control')
    for bad in ([], [(0, 10)], [(0, 10), (11, 20)]):
        try:
            request_groups(bad)
        except GateError:
            continue
        raise GateError('C54 request segmentation negative control')
    if MARKER.fullmatch('C46_WAVE_LAYER=25_WAVE=2_ACTIVE=13_OF=128') is None or \
       MARKER.fullmatch('C46_WAVE_LAYER=x_WAVE=2_ACTIVE=13_OF=128') is not None:
        raise GateError('C54 wave marker controls')


def main():
    test()
    output = ROOT/'phase-summary.json'
    if output.exists():
        raise GateError('C54 phase summary no-replace')
    receipt_path = ROOT/f'{campaign.RUN_ID}-receipt.json'
    raw_path = ROOT/'raw'/f'{campaign.RUN_ID}.json'
    report = ROOT/'raw/c54-phase-profile.nsys-rep'
    db_path = ROOT/'raw/c54-phase-profile.sqlite'
    receipt = strict_json(receipt_path.read_text())
    raw = strict_json(raw_path.read_text())
    if receipt['status'] != 'PASS_DIAGNOSTIC_OUTPUT_BRIDGE' or \
       receipt['raw_sha256'] != sha256(raw_path) or \
       raw['returncode'] != 0 or raw['stop_reasons'] or \
       len(raw['results']) != 2 or not report.is_file() or not db_path.is_file() or \
       report.stat().st_size > 2*2**30:
        raise GateError('C54 output bridge or profiler raw invalid')
    pid = raw['launch_identity']['pid']
    with sqlite3.connect(db_path) as db:
        tables = {name for (name,) in db.execute("select name from sqlite_master where type='table'")}
        if not {'PROCESSES', 'NVTX_EVENTS'} <= tables:
            raise GateError('C54 profiler process/NVTX table absent')
        processes = db.execute('select globalPid,name from PROCESSES where pid=?', (pid,)).fetchall()
        if len(processes) != 1 or processes[0][1] != 'llama-server':
            raise GateError('C54 model PID ambiguous')
        global_pid = processes[0][0]
        ranges = {}
        for label in LABELS:
            rows = db.execute('select start,end,eventType,globalTid from NVTX_EVENTS where text=?',
                              (label,)).fetchall()
            if not rows or any(kind != 59 or end is None or (tid & ~0xffffff) != global_pid
                               for _, end, kind, tid in rows):
                raise GateError(f'C54 NVTX range missing/invalid: {label}')
            ranges[label] = [(start, end) for start, end, _, _ in rows]
        marks = db.execute("select start,end,eventType,text,globalTid from NVTX_EVENTS where text like 'C46_WAVE_%'").fetchall()
    prefill_groups = request_groups(ranges[LABELS[0]])
    first, warm = map(merge, prefill_groups)
    if warm[0][0] - first[-1][1] < 120_000_000_000 or \
       intersect(first, warm) or intersect(warm, ranges[LABELS[1]]):
        raise GateError('C54 request/phase ordering invalid')
    mmid = intersect(ranges['C15_CPU_STREAM_MATMUL_ID'], warm)
    pread = intersect(ranges['C15_EXPERT_PREAD'], warm)
    upload = intersect(ranges['C15_EXPERT_UPLOAD'], warm)
    tagged_io = merge(pread + upload)
    overlap = intersect(mmid, tagged_io)
    waves = []
    for start, end, kind, label, tid in marks:
        match = MARKER.fullmatch(label or '')
        if kind != 34 or end is not None or (tid & ~0xffffff) != global_pid or not match:
            raise GateError('C54 wave marker malformed')
        layer, wave, active, all_slots = map(int, match.groups())
        if layer > 35 or wave > 255 or all_slots == 0 or active > all_slots:
            raise GateError('C54 wave marker values invalid')
        if any(a <= start <= b for a, b in warm):
            waves.append((layer, wave, active, all_slots))
    if not mmid or not pread or not upload or not waves:
        raise GateError('C54 warm-prefill diagnostic coverage incomplete')
    all_pairs = sum(row[3] for row in waves)
    result = {
        'schema':'c54-warm-phase-summary-v1', 'status':'DIAGNOSTIC_INTERVAL_COVERAGE',
        'model_pid':pid,'nsys_global_pid':global_pid,
        'first_prefill_decode_union_s':duration_ns(first)/1e9,
        'warm_prefill_decode_union_s':duration_ns(warm)/1e9,
        'warm_mmid_interval_count':len(mmid),
        'warm_mmid_union_s':duration_ns(mmid)/1e9,
        'warm_pread_union_s':duration_ns(pread)/1e9,
        'warm_upload_union_s':duration_ns(upload)/1e9,
        'warm_tagged_io_union_s':duration_ns(tagged_io)/1e9,
        'warm_mmid_tagged_io_overlap_s':duration_ns(overlap)/1e9,
        'warm_mmid_without_tagged_io_s':(duration_ns(mmid)-duration_ns(overlap))/1e9,
        'warm_wave_marker_count':len(waves),
        'warm_active_pairs':sum(row[2] for row in waves),
        'warm_all_pair_slots':all_pairs,
        'warm_active_pair_fraction':sum(row[2] for row in waves)/all_pairs,
        'warm_zero_active_wave_count':sum(row[2]==0 for row in waves),
        'parent_c52b_warm_prefill_s':receipt['results'][1]['timings']['prompt_ms']/1000,
        'limits':['NVTX instrumented timing is diagnostic, not production timing',
                  'interval union and non-overlap do not prove removable exclusive critical-path work',
                  'MMID tag specificity and wave association are source inferred',
                  '/proc I/O accounting is not exclusive physical NVMe traffic',
                  'output bridge covers two finite messages and token IDs, not full logits'],
        'raw_sha256':{str(p):sha256(p) for p in (receipt_path,raw_path,report,db_path)},
        'analyzer_sha256':sha256(__file__),
    }
    if not 0 <= result['warm_mmid_without_tagged_io_s'] <= result['warm_mmid_union_s'] <= \
       result['warm_prefill_decode_union_s'] or not 0 < result['warm_active_pair_fraction'] <= 1:
        raise GateError('C54 interval arithmetic invalid')
    with output.open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')
    print(json.dumps({'status':result['status'],
                      'warm_prefill_s':result['warm_prefill_decode_union_s'],
                      'mmid_without_io_s':result['warm_mmid_without_tagged_io_s']}))


if __name__ == '__main__':
    main()
