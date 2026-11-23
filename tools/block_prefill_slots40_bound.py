"""Reuse C135 without inventing initial residency, token routing or commit time."""
import argparse
from collections import Counter
import json
from pathlib import Path

import c135_analyze_slots40_trace as original
from c123_analyze_trace import trace_rows
from c122_trace_validate import validate, union_us
from run_bounded import sha256


def layer_bound(events, metadata):
    demands = [e for e in events if e['kind'] == 'DEMAND']
    loads = [e for e in events if e['kind'] == 'LOAD_BEGIN']
    required = {e['expert'] for e in demands}
    if not required or any(not 0 <= e < 128 for e in required):
        raise ValueError('missing authoritative demanded expert union')
    # First ready observations need not describe the initial cache: a previous
    # tile may have loaded them. Never turn them into initial-ready credits.
    seen = set(); repeated = set()
    for e in events:
        if e['kind'] == 'DEMAND' and e['state'] == 2:
            seen.add(e['expert'])
        if e['kind'] == 'LOAD_BEGIN':
            key = (e['slot'], e['generation'])
            if key in repeated:
                raise ValueError('duplicate load generation')
            if e['expert'] in seen:
                repeated.add(key)
            seen.add(e['expert'])
    starts = {}; waits = []; eligible = []
    for e in events:
        key = (e['call_id'], e['wave'], e['n_tokens'])
        if e['kind'] == 'WAIT_BEGIN':
            if key in starts: raise ValueError('duplicate barrier')
            starts[key] = e['mono_us']
        if e['kind'] == 'WAIT_END':
            a, b = starts.pop(key), e['mono_us']
            waits.append((a, b))
            if any(x['kind'] == 'LOAD_END' and
                   (x['slot'], x['generation']) in repeated and
                   a <= x['mono_us'] <= b for x in events):
                eligible.append((a, b))
    if starts: raise ValueError('incomplete barrier')
    counts = Counter(e['expert'] for e in loads)
    minimum = max(0, len(required) - 40)
    return dict(demanded_union=sorted(required), union_count=len(required),
                actual_loads=len(loads), actual_logical_bytes=len(loads)*metadata['bytes'],
                repeated_after_observed_ready_or_load=len(repeated),
                unconsumed_loads=sum(n for e, n in counts.items() if e not in required),
                optimistic_minimum_service_loads=minimum,
                optimistic_minimum_logical_bytes=minimum*metadata['bytes'],
                initial_ready='UNKNOWN; optimistic bound credits up to all 40 slots',
                waits=waits, duplicate_eligible_waits=eligible)


def analyze():
    previous = original.analyze()  # Revalidates raw manifests, IDs and call plan.
    path = original.ROOT_ON/'raw'/f'{original.ON}.expert.trace'
    parsed = validate(path); metadata, events = trace_rows(path)
    rows = []; waits = []; eligible = []
    for layer in range(36):
        es = [e for e in events if e['layer'] == layer and e['call_id'] in (1,2)]
        row = layer_bound(es, metadata[layer])
        lw, le = row.pop('waits'), row.pop('duplicate_eligible_waits')
        row.update(layer=layer, tier=metadata[layer]['device'],
                   wait_union_s=union_us(lw)/1e6,
                   eligible_whole_barrier_s=union_us(le)/1e6)
        rows.append(row); waits += lw; eligible += le
    duration = sum(parsed['calls'][i]['end_us']-parsed['calls'][i]['start_us']
                   for i in (1,2))/1e6
    keys = ('actual_loads','actual_logical_bytes','repeated_after_observed_ready_or_load',
            'optimistic_minimum_service_loads','optimistic_minimum_logical_bytes','unconsumed_loads')
    return dict(schema='c261-slots40-prefill-bound-v1',
        evidence='SOURCE_AUDITED / existing MEDIDO_NO_TARGET / ESTIMADO counterfactual',
        trace_sha256=sha256(path), prior_revalidation=previous,
        scope='C135 slots40 server trace-on, 2026-09-29, external5+148 and internal numerical tiles; not new R2 routing or production timing',
        prefill_call_s=duration, layers=rows,
        tiers={tier:{key:sum(r[key] for r in rows if r['tier']==tier) for key in keys}
               for tier in ('CPU','CUDA0')},
        exposed_wait_union_s=union_us(waits)/1e6,
        optimistic_eligible_whole_barrier_s=union_us(eligible)/1e6,
        optimistic_eligible_prefill_percent=100*union_us(eligible)/1e6/duration,
        assumptions=['Observed byte-service times fixed; remove entire eligible barriers, even when they also contain unavoidable work.',
            'Zero new scheduling/copies/attention overhead; no changed contention. This is an optimistic scenario, not a rigorous server bound.',
            'LOAD_END is not RESIDENT_COMMIT. Missing precise commit can omit eligible waits; no invented timestamps.',
            'No initial full snapshot or per-token ordered routes/activations. Capacity40 credit is only an optimistic logical lower bound.',
            'Logical loads/bytes are not physical NVMe traffic. C260 service gains are not multiplied into this denominator.'],
        decision='GO_BOUNDED_LAYER_EXECUTOR_PROTOTYPE_OPPORTUNITY_NOT_SPEEDUP')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);a=parser.parse_args()
    with a.output.open('x') as f: json.dump(analyze(), f, indent=2, allow_nan=False);f.write('\n')

if __name__=='__main__':main()
