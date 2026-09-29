"""Reanalyse the frozen C123 warm153 trace without loading the model.

The counterfactual cache below is deliberately narrow: a separate RAM copy is
inserted only after a completed load, and consulted at the next load start.
It leaves the observed primary cache and its miss stream fixed. Consequently
it measures possible logical read avoidance on this trace, not elapsed gain.
"""

import argparse
import hashlib
import json
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

from c122_trace_validate import HEADER, union_us, validate
from c2_gate import GateError

GIB = 2**30
EXPECTED_TRACE_SHA = 'c47d8fcd3056d41fd448c2a45d619153418dad89567bfa5ab4dd2aa5a8b86f3a'
EXPECTED_RAW_SHA = 'd9d2669019afecbad5349c3cf33913ecb85ba43391ae0ee4a94125bdace5501e'
EXPECTED_RUN = 'c123-c75-warm153'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def trace_rows(path):
    lines = Path(path).read_text().splitlines()
    layer = {}
    for line in lines:
        if line.startswith('L\t'):
            _, n, size, device = line.split('\t')
            n = int(n)
            if n in layer or device not in ('CPU', 'CUDA0') or int(size) <= 0:
                raise GateError('invalid layer metadata')
            layer[n] = {'bytes': int(size), 'device': device}
    if sorted(layer) != list(range(36)):
        raise GateError('incomplete layer metadata')
    header = lines.index('\t'.join(HEADER))
    rows = []
    for line in lines[header+1:-1]:
        cells = line.split('\t')
        rows.append(dict(zip(HEADER, [cells[0]] + [int(v) for v in cells[1:]])))
    return layer, rows


def phase(cid):
    return 'prefill' if cid <= 2 else 'decode'


def summarize_spans(rows, layers):
    starts = {}
    stats = defaultdict(lambda: defaultdict(list))
    pair_names = ('WAIT', 'READ', 'TENSOR_SET', 'LOAD', 'VICTIM_WAIT', 'MUTEX_WAIT')
    for e in rows:
        kind = e['kind']
        p = phase(e['call_id'])
        if kind == 'READ_BEGIN':
            stats[p]['logical_read_bytes'].append(e['logical_bytes'])
        if kind == 'LOAD_BEGIN':
            stats[p]['load_bytes'].append(e['logical_bytes'])
        if kind == 'DEMAND':
            stats[p]['demand_states'].append(e['state'])
        if kind == 'ENQUEUE':
            starts[('QUEUE', e['layer'], e['expert'], e['slot'], e['generation'])] = e['mono_us']
        if kind == 'DEQUEUE':
            key = ('QUEUE', e['layer'], e['expert'], e['slot'], e['generation'])
            if key not in starts:
                raise GateError('orphan dequeue')
            stats[p]['QUEUE'].append((starts.pop(key), e['mono_us']))
        for name in pair_names:
            if kind == name + '_BEGIN':
                key = (name, e['call_id'], e['layer'], e['expert'], e['slot'], e['generation'], e['component'], e['wave'])
                starts[key] = e['mono_us']
            if kind == name + ('_RETURN' if name == 'TENSOR_SET' else '_END'):
                key = (name, e['call_id'], e['layer'], e['expert'], e['slot'], e['generation'], e['component'], e['wave'])
                if key not in starts:
                    raise GateError('orphan analysis span')
                a = starts.pop(key)
                if e['mono_us'] < a:
                    raise GateError('negative analysis span')
                stats[p][name].append((a, e['mono_us']))
                if name == 'WAIT':
                    device = layers[e['layer']]['device']
                    stats[p]['WAIT_' + device].append((a, e['mono_us']))
    if starts:
        raise GateError('incomplete analysis span')
    out = {}
    for p, values in stats.items():
        out[p] = {}
        for k, v in values.items():
            if k.endswith('_bytes'):
                out[p][k] = sum(v)
            elif k == 'demand_states':
                out[p][k] = dict(Counter(v))
            else:
                out[p][k] = {'count': len(v), 'sum_s': sum(b-a for a,b in v)/1e6,
                             'union_s': union_us(v)/1e6}
    return out


def simulate_completed_lru(rows, layers, budget_bytes, gpu_only=False):
    # Timestamp order is required because the backend publishes some start/end
    # records together after the worker completes. Equal timestamps use seq.
    events = sorted((e for e in rows if e['kind'] in ('LOAD_BEGIN', 'LOAD_END')),
                    key=lambda e: (e['mono_us'], e['seq']))
    cache = OrderedDict()
    used = 0
    hits = Counter()
    load_counts = Counter()
    hit_bytes = Counter()
    for e in events:
        if gpu_only and layers[e['layer']]['device'] != 'CUDA0':
            continue
        p = phase(e['call_id'])
        key = (e['layer'], e['expert'])
        size = layers[e['layer']]['bytes']
        if e['kind'] == 'LOAD_BEGIN':
            load_counts[p] += 1
            if key in cache:
                hits[p] += 1
                hit_bytes[p] += size
                cache.move_to_end(key)
        elif e['kind'] == 'LOAD_END' and size <= budget_bytes:
            if key in cache:
                cache.move_to_end(key)
            else:
                while used + size > budget_bytes:
                    old, old_size = cache.popitem(last=False)
                    used -= old_size
                cache[key] = size
                used += size
    return {'load_counts': dict(load_counts), 'hits': dict(hits),
            'logical_bytes_avoided': dict(hit_bytes),
            'decode_hit_fraction': hits['decode'] / load_counts['decode'] if load_counts['decode'] else None,
            'policy': 'timestamp ordered, completed load insertion; fixed observed primary miss stream; zero insertion cost'}


def analyze(root):
    root = Path(root)
    rawdir = root / 'raw'
    prefix = EXPECTED_RUN
    trace = rawdir / (prefix + '.expert.trace')
    raw = rawdir / (prefix + '.json')
    receipt = json.loads((rawdir / (prefix + '.receipt.json')).read_text())
    if sha(trace) != EXPECTED_TRACE_SHA or sha(raw) != EXPECTED_RAW_SHA:
        raise GateError('C123 frozen raw SHA mismatch')
    if receipt['status'] != 'PASS_DIAGNOSTIC_CAPTURE' or receipt['run_id'] != prefix:
        raise GateError('C123 receipt identity/status invalid')
    if receipt['trace_sha256'] != sha(trace) or receipt['raw_sha256'] != sha(raw):
        raise GateError('C123 receipt hash mismatch')
    parsed = validate(trace)
    layers, rows = trace_rows(trace)
    markers = [json.loads(line) for line in (rawdir / (prefix + '.request-markers.jsonl')).read_text().splitlines()]
    trigger = json.loads((rawdir / (prefix + '.trace-trigger.json')).read_text())
    expected_markers = [('c112-code', 'REQUEST_START'), ('c112-code', 'RESPONSE_COMPLETE'),
                        ('c112-repeat', 'REQUEST_START'), ('c112-repeat', 'RESPONSE_COMPLETE')]
    if [(x['request_id'], x['kind']) for x in markers] != expected_markers or any(x['run_id'] != prefix for x in markers):
        raise GateError('C123 request marker order/identity invalid')
    if not (markers[0]['mono_ns'] < markers[1]['mono_ns'] < trigger['mono_ns'] < markers[2]['mono_ns'] < markers[3]['mono_ns']):
        raise GateError('C123 trigger/request order invalid')
    if trigger['run_id'] != prefix or trigger['request_id'] != 'c112-repeat':
        raise GateError('C123 trigger identity invalid')
    calls = {int(k):v for k,v in parsed['calls'].items()}
    if len(calls) != 48 or [(calls[i]['n_tokens'], calls[i]['first_pos'], calls[i]['last_pos']) for i in (1,2)] != [(5,2044,2048),(148,2049,2196)]:
        raise GateError('C123 warm prefill call plan invalid')
    if any((calls[i]['n_tokens'],calls[i]['first_pos'],calls[i]['last_pos']) != (1,2194+i,2194+i) for i in range(3,49)):
        raise GateError('C123 decode call plan invalid')
    if not (markers[2]['mono_ns']//1000 <= calls[1]['start_us'] < calls[48]['end_us'] <= markers[3]['mono_ns']//1000):
        raise GateError('C123 trace outside request markers')
    obj = json.loads(raw.read_text())
    if obj['returncode'] != 0 or obj['stop_reasons'] or len(obj['results']) != 2:
        raise GateError('C123 server run invalid')
    a,b = obj['results']
    if [(x['id'],x['finish_reason']) for x in (a,b)] != [('c112-code','stop'),('c112-repeat','stop')]:
        raise GateError('C123 responses invalid')
    if (a['usage']['prompt_tokens'],a['usage']['completion_tokens']) != (2043,78) or (b['usage']['prompt_tokens'],b['usage']['completion_tokens'],b['usage']['prompt_tokens_details']['cached_tokens']) != (2197,47,2044):
        raise GateError('C123 official tokens invalid')
    spans = summarize_spans(rows,layers)
    duration = {p:sum((calls[i]['end_us']-calls[i]['start_us']) for i in ids)/1e6 for p,ids in [('prefill',[1,2]),('decode',range(3,49))]}
    cache = {}
    for name, gpu in [('global',False),('gpu_only',True)]:
        cache[name] = {str(g):simulate_completed_lru(rows,layers,g*GIB,gpu) for g in (1,2,3)}
    target_decode_s = 47/6
    observed_decode_s = b['timings']['predicted_ms']/1000
    return {'schema':'c123-analysis-v1','evidence':'MEDIDO_NO_TARGET',
            'trace_sha256':sha(trace),'server_raw_sha256':sha(raw),
            'request':'c112-repeat','tokens':{'new_prompt':153,'cached_prompt':2044,'output':47,'traced_decode_evaluations':46},
            'layer_devices':dict(Counter(v['device'] for v in layers.values())),
            'trace':{'events':parsed['events'],'loads':parsed['loads'],'calls':len(calls),'call_duration_s':duration,'spans':spans},
            'server':{'warm_first_final_s':b['stream_metrics']['time_to_first_final_s'] if 'time_to_first_final_s' in b['stream_metrics'] else None,
                      'warm_prefill_s':b['timings']['prompt_ms']/1000,'warm_decode_s':observed_decode_s,
                      'warm_decode_tok_s':b['timings']['predicted_per_second']},
            'conditional_bounds':{'decode_target_6tok_s':target_decode_s,
                                  'decode_saving_required_s':observed_decode_s-target_decode_s,
                                  'observed_wait_union_s':spans['decode']['WAIT']['union_s'],
                                  'fraction_of_wait_required_if_rest_fixed':(observed_decode_s-target_decode_s)/spans['decode']['WAIT']['union_s']},
            'cache_fixed_stream_completed_lru':cache,
            'limitations':['Read bytes are logical expert slab bytes, not physical NVMe controller bytes.',
                           'WAIT is observed readiness blocking, not automatically removable time.',
                           'READ intervals overlap; sum is worker time, union is elapsed coverage.',
                           'Cache simulation fixes the primary miss stream and assumes free insertion; it is not a time prediction.',
                           'Trace-on timing has no same-binary neutral A/B yet.']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    result = analyze(args.root)
    encoded = json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded)
