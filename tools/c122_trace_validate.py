"""Validate the bounded C122 expert trace and summarize observed intervals."""

from collections import Counter, defaultdict
from pathlib import Path

from c2_gate import GateError

HEADER = ('kind seq mono_us layer expert slot victim n_tokens wave state '
          'logical_bytes call_id generation component').split()
PAIRS = {'CALL_BEGIN': 'CALL_END', 'READ_BEGIN': 'READ_END',
         'TENSOR_SET_BEGIN': 'TENSOR_SET_RETURN',
         'WAIT_BEGIN': 'WAIT_END', 'VICTIM_WAIT_BEGIN': 'VICTIM_WAIT_END',
         'MUTEX_WAIT_BEGIN': 'MUTEX_WAIT_END', 'LOAD_BEGIN': 'LOAD_END'}


def union_us(spans):
    merged = []
    for start, end in sorted(spans):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(end, merged[-1][1])
    return sum(end - start for start, end in merged)


def validate(path, *, max_bytes=64 * 2**20):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise GateError('C122 trace missing or above 64 MiB')
    lines = path.read_text().splitlines()
    if not lines or lines[0] != '#c122-expert-decode-v1':
        raise GateError('C122 trace header invalid')
    table = next((i for i, line in enumerate(lines) if line.startswith('kind\t')), None)
    if table is None or lines[table].split('\t') != HEADER or table < 2:
        raise GateError('C122 trace columns invalid')
    events = []
    for seq, line in enumerate(lines[table+1:-1]):
        parts = line.split('\t')
        if len(parts) != len(HEADER):
            raise GateError('C122 event column count invalid')
        try:
            row = dict(zip(HEADER, [parts[0]] + [int(v) for v in parts[1:]]))
        except ValueError as exc:
            raise GateError('C122 event number invalid') from exc
        if row['seq'] != seq or row['mono_us'] < 0 or row['call_id'] < 1:
            raise GateError('C122 event seq/time/call invalid')
        events.append(row)
    if lines[-1] != f'#end\t{len(events)}\t0':
        raise GateError('C122 event count/overflow invalid')
    by_kind = Counter(e['kind'] for e in events)
    calls = {}
    open_pairs = {}
    spans = defaultdict(list)
    loads = defaultdict(dict)
    for e in events:
        kind = e['kind']
        if kind == 'CALL_BEGIN':
            cid = e['call_id']
            if cid in calls or cid != len(calls) + 1:
                raise GateError('C122 duplicate/out-of-order call')
            calls[cid] = {'start_us': e['mono_us'], 'n_tokens': e['n_tokens'],
                          'first_pos': e['expert'], 'last_pos': e['slot']}
        elif e['call_id'] not in calls:
            raise GateError('C122 event without prior call')
        if kind in PAIRS:
            key = (kind, e['call_id'], e['layer'], e['expert'], e['slot'],
                   e['generation'], e['component'], e['wave'])
            if key in open_pairs:
                raise GateError('C122 duplicate BEGIN')
            open_pairs[key] = e['mono_us']
        elif kind in PAIRS.values():
            start_kind = next(k for k, v in PAIRS.items() if v == kind)
            key = (start_kind, e['call_id'], e['layer'], e['expert'], e['slot'],
                   e['generation'], e['component'], e['wave'])
            if key not in open_pairs:
                raise GateError('C122 orphan/duplicate END')
            begin = open_pairs.pop(key)
            if e['mono_us'] < begin:
                raise GateError('C122 negative interval')
            spans[start_kind].append((begin, e['mono_us'], e['call_id']))
            if kind == 'CALL_END':
                calls[e['call_id']]['end_us'] = e['mono_us']
            if kind == 'LOAD_END':
                loads[(e['layer'], e['expert'], e['slot'], e['generation'])]['complete'] = True
        if kind == 'DEQUEUE':
            key = (e['layer'], e['expert'], e['slot'], e['generation'])
            if 'dequeued' in loads[key]:
                raise GateError('C122 duplicate load dequeue')
            loads[key]['dequeued'] = e['mono_us']
        if kind == 'LOAD_BEGIN':
            key = (e['layer'], e['expert'], e['slot'], e['generation'])
            if 'began' in loads[key]:
                raise GateError('C122 duplicate load start')
            loads[key]['began'] = e['mono_us']
        if kind == 'LOAD_ERROR':
            raise GateError('C122 traced load error')
    if open_pairs or not calls or any('end_us' not in c for c in calls.values()):
        raise GateError('C122 incomplete interval/call')
    if any(not {'dequeued', 'began', 'complete'} <= set(v) for v in loads.values()):
        raise GateError('C122 incomplete load generation')
    if any(c['n_tokens'] <= 0 or c['end_us'] < c['start_us'] for c in calls.values()):
        raise GateError('C122 invalid call duration')
    return {'schema':'c122-trace-summary-v1','events':len(events),
            'calls':calls,'counts':dict(by_kind),'loads':len(loads),
            'span_sum_us':{k:sum(b-a for a,b,_ in v) for k,v in spans.items()},
            'span_union_us':{k:union_us((a,b) for a,b,_ in v) for k,v in spans.items()},
            'trace_bytes':path.stat().st_size}
