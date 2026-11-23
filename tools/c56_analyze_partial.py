#!/usr/bin/env python3
"""Exploratory phase bounds from the preserved owner-interrupted C54 trace."""
import json
from pathlib import Path
import sqlite3

from c2_gate import GateError,strict_json
from c46_analyze import merge,intersect,duration_ns,MARKER
from c54_analyze import request_groups
from run_bounded import sha256

C54=Path('results/c54-warm-phase-20260928T1304Z')
ROOT=Path('results/c56-c54-partial-20260928T1420Z')
LABELS=('C46_SERVER_PREFILL_DECODE','C46_SERVER_GENERATION_DECODE',
        'C15_CPU_STREAM_MATMUL_ID','C15_EXPERT_PREAD','C15_EXPERT_UPLOAD')

def main():
    output=ROOT/'phase-partial.json'
    if output.exists():raise GateError('C56 no-replace')
    manifest=strict_json((C54/'manifest.json').read_text())
    for section in ('raw_local_sha256','compact_sha256'):
        for path,want in manifest[section].items():
            if sha256(path)!=want:raise GateError('C54 source hash mismatch: '+path)
    receipt=strict_json((C54/'c54-p12-assistant-history01-receipt.json').read_text())
    raw=strict_json((C54/'raw/c54-p12-assistant-history01.json').read_text())
    if receipt['status']!='FAIL_RESOURCES_OR_EVIDENCE' or \
       raw['stop_reasons']!=['RUN_ERROR:GateError:incomplete stream completion/usage/timings fence'] or \
       len(raw['results'])!=1:
        raise GateError('C54 interruption evidence changed')
    db_path=ROOT/'raw/c54-partial.sqlite'
    if not db_path.is_file():raise GateError('C56 SQLite export absent')
    with sqlite3.connect(db_path) as db:
        pid=raw['launch_identity']['pid']
        processes=db.execute('select globalPid,name from PROCESSES where pid=?',(pid,)).fetchall()
        if len(processes)!=1 or processes[0][1]!='llama-server':
            raise GateError('C56 model process ambiguity')
        global_pid=processes[0][0]
        intervals={}
        for label in LABELS:
            rows=db.execute('select start,end,eventType,globalTid from NVTX_EVENTS where text=?',
                            (label,)).fetchall()
            if not rows or any(kind!=59 or end is None or (tid & ~0xffffff)!=global_pid
                               for _,end,kind,tid in rows):
                raise GateError('C56 range missing/corrupt: '+label)
            intervals[label]=[(start,end) for start,end,_,_ in rows]
        marks=db.execute("select start,end,eventType,text,globalTid from NVTX_EVENTS where text like 'C46_WAVE_%'").fetchall()
    first,warm=(merge(g) for g in request_groups(intervals[LABELS[0]]))
    generation=merge(intervals[LABELS[1]])
    if not generation or generation[-1][1]>=warm[0][0] or \
       not 160 <= (warm[0][0]-generation[-1][1])/1e9 <= 172:
        raise GateError('C56 frozen 165s idle/phase association failed')
    mmid=intersect(intervals['C15_CPU_STREAM_MATMUL_ID'],warm)
    pread=intersect(intervals['C15_EXPERT_PREAD'],warm)
    upload=intersect(intervals['C15_EXPERT_UPLOAD'],warm)
    io=merge(pread+upload)
    overlap=intersect(mmid,io)
    waves=[]
    for start,end,kind,label,tid in marks:
        match=MARKER.fullmatch(label or '')
        if kind!=34 or end is not None or (tid & ~0xffffff)!=global_pid or not match:
            raise GateError('C56 invalid wave marker')
        layer,wave,active,total=map(int,match.groups())
        if layer>35 or wave>255 or total==0 or active>total:
            raise GateError('C56 invalid wave values')
        if any(a<=start<=b for a,b in warm):waves.append((layer,wave,active,total))
    if not mmid or not pread or not upload or not waves:
        raise GateError('C56 warm phase marker coverage missing')
    # Align Nsight monotonic clock with the first request; record residual,
    # without treating the unfinished second response as a completion fence.
    first_start=raw['results'][0]['started_s']
    report_to_server_offset=first[0][0]/1e9-first_start
    warm_end_server_s=warm[-1][1]/1e9-report_to_server_offset
    boundary_gap_s=raw['elapsed_s']-warm_end_server_s
    if not 0 <= boundary_gap_s <= 5:
        raise GateError('C56 warm closed range cannot be aligned before interruption')
    pairs=sum(x[3] for x in waves)
    result={'schema':'c56-partial-phase-v1','status':'EXPLORATORY_CLOSED_WARM_PREFILL_RANGES',
            'source_run_status':'INTERRUPTED_BY_OWNER','complete_second_response':False,
            'model_pid':pid,'first_prefill_ranges':len(first),'warm_prefill_ranges':len(warm),
            'first_generation_ranges':len(generation),'warm_prefill_decode_union_s':duration_ns(warm)/1e9,
            'warm_mmid_union_s':duration_ns(mmid)/1e9,
            'warm_pread_union_s':duration_ns(pread)/1e9,
            'warm_upload_union_s':duration_ns(upload)/1e9,
            'warm_tagged_io_union_s':duration_ns(io)/1e9,
            'warm_mmid_tagged_io_overlap_s':duration_ns(overlap)/1e9,
            'warm_mmid_without_tagged_io_s':(duration_ns(mmid)-duration_ns(overlap))/1e9,
            'warm_wave_marks':len(waves),'warm_active_pairs':sum(x[2] for x in waves),
            'warm_all_pair_slots':pairs,'warm_active_pair_fraction':sum(x[2] for x in waves)/pairs,
            'warm_zero_active_wave_marks':sum(x[2]==0 for x in waves),
            'first_generation_to_warm_prefill_gap_s':(warm[0][0]-generation[-1][1])/1e9,
            'closed_warm_range_to_interruption_s':boundary_gap_s,
            'claims':['NVTX intervals are diagnostic under instrumentation',
                      'warm prefill decode ranges are closed before owner interruption',
                      'second API completion/cache count and full output bridge remain missing',
                      'MMID non-overlap is not demonstrated removable critical-path time',
                      'read/upload tags are not independent physical NVMe/block traffic'],
            'source_sha256':{str(p):sha256(p) for p in (db_path,C54/'manifest.json',
                C54/'raw/c54-phase-profile.nsys-rep',C54/'raw/c54-p12-assistant-history01.json')},
            'analyzer_sha256':sha256(__file__)}
    if not 0 <= result['warm_mmid_without_tagged_io_s'] <= result['warm_mmid_union_s'] <= \
       result['warm_prefill_decode_union_s']:
        raise GateError('C56 interval arithmetic inconsistent')
    with output.open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],
                      'warm_prefill_decode_union_s':result['warm_prefill_decode_union_s'],
                      'warm_mmid_without_tagged_io_s':result['warm_mmid_without_tagged_io_s'],
                      'warm_active_pair_fraction':result['warm_active_pair_fraction']}))

if __name__=='__main__':main()
