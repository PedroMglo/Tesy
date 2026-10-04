"""Reuse qualified warm-prefill journals; logical bytes and conditional waits.

No replay replacement or physical-NVMe claim. In-flight initial loads remain
required service, and initial ready copies are identified separately.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from c122_trace_validate import union_us
from c152_journal_validate import validate
from c152_snapshot_read import routes, snapshot
from readiness_feasibility import check_manifest


def logical_bound(tile_ids, initial_ready, initial_loading, loads, expert_bytes):
    if not tile_ids or expert_bytes <= 0:
        raise ValueError('missing tiles/bytes')
    for tile in tile_ids:
        if not tile or len(tile) % 4 or any(type(x) is not int or not 0 <= x < 128 for x in tile):
            raise ValueError('authoritative top-k rows missing')
        if any(len(set(tile[i:i+4])) != 4 for i in range(0, len(tile), 4)):
            raise ValueError('duplicate expert within token')
    ready, loading = set(initial_ready), set(initial_loading)
    if ready & loading:
        raise ValueError('initial slot cannot be ready and loading')
    required = set(x for tile in tile_ids for x in tile)
    counts = Counter(e['expert'] for e in loads)
    # This charges all required nonresident bytes, including already in-flight.
    service_min = len(required - ready)
    future_initiations_min = len(required - ready - loading)
    duplicates = sum(max(0, count - 1) for expert, count in counts.items()
                     if expert in required)
    initial_ready_reloads = sum(counts[e] for e in required & ready)
    distances = []; previous = {}
    for tile_index, tile in enumerate(tile_ids):
        for expert in dict.fromkeys(tile):
            if expert in previous:
                distances.append(tile_index - previous[expert])
            previous[expert] = tile_index
    return dict(tile_count=len(tile_ids), token_rows=sum(len(t)//4 for t in tile_ids),
                demanded_union=sorted(required), union_count=len(required),
                initial_ready_selected=sorted(required & ready),
                initial_loading_selected=sorted(required & loading),
                minimum_required_service_bytes=service_min * expert_bytes,
                minimum_future_initiation_bytes=future_initiations_min * expert_bytes,
                observed_loads=len(loads), observed_logical_bytes=len(loads)*expert_bytes,
                repeated_selected_loads=duplicates,
                initially_ready_selected_reload_count=initial_ready_reloads,
                loads_not_consumed_in_this_phase=sum(n for e, n in counts.items() if e not in required),
                tile_reuse_distance_histogram=dict(Counter(distances)),
                assumption='Perfect reuse may require scheduling/buffers beyond the baseline; in-flight service is not free. Initial ready retention is conditional, not demonstrated capacity.')


def case(directory, run):
    cap = Path(run['command'][-1]); initial = snapshot(cap/'before-warm.snap')
    final = snapshot(cap/'after-prefill.snap')
    trace = Path(run['env']['TESY_C84_EXPERT_TRACE_FILE']+'.window.trace')
    route_path = Path(run['env']['TESY_C152_ROUTE_FILE'])
    journal = validate(trace, initial=initial); routing = routes(route_path)
    lo, hi = initial['mono_us'], final['mono_us']
    calls = {cid: row for cid, row in journal['calls'].items() if
             row['begin']['expert'] >= initial['first_pos'] and
             row['begin']['expert'] <= initial['last_pos'] and
             row['begin']['n_tokens'] > 1}
    if set(calls) != {9, 10}:
        raise ValueError('expected provided warm5+148 call plan')
    selected = [r for r in routing if r['call_id'] in calls]
    rows = []; all_waits = []; duplicate_waits = []
    for layer, sl in enumerate(initial['layers']):
        tile_ids = [r['ids'] for r in selected if r['layer'] == layer]
        ready = [e for e,s in zip(sl['slot_expert'], sl['slot_state']) if s == 2]
        loading = [e for e,s in zip(sl['slot_expert'], sl['slot_state']) if s == 1]
        events = [e for e in journal['rows'] if e['layer'] == layer]
        loads = [e for e in events if e['kind'] == 'LOAD_BEGIN' and
                 lo <= e['mono_us'] <= hi]
        loads.sort(key=lambda e: (e['mono_us'], e['work_id']))
        size = sum(c['expert_bytes'] for c in sl['components'])
        row = logical_bound(tile_ids, ready, loading, loads, size)
        demand_work = {e['work_id'] for e in events if e['kind'] == 'ENQUEUE' and
                       e['call_id'] in calls and e['state'] == 1}
        # Origins are retained rather than inferring demand from bytes alone.
        row['enqueue_origins'] = dict(Counter(e['kind'] for e in events if
                                            e['kind'] in ('DEMAND','PRELOAD') and e['call_id'] in calls))
        row['new_phase_work_ids'] = len(demand_work)
        seen = set(ready) | set(loading); repeated_work = set()
        inherited_work = {w['work_id'] for w in initial['queue'] +
                          [w for w in initial['owned'] if w['phase']]}
        for e in loads:
            if e['expert'] in seen and e['work_id'] not in inherited_work:
                repeated_work.add(e['work_id'])
            seen.add(e['expert'])
        barriers = [b for b in journal['barriers'] if b['begin']['layer'] == layer and
                    b['begin']['call_id'] in calls]
        spans = [(b['begin']['mono_us'], b['end']['mono_us']) for b in barriers]
        eligible = [(b['begin']['mono_us'], b['end']['mono_us']) for b in barriers
                    if any(e['work_id'] in repeated_work for e in b['blocking_commits'])]
        # Deliberately coarse ceiling: erase the whole eligible barrier even when
        # it also waits for unavoidable loads. Not a predicted removable duration.
        row.update(layer=layer, tier='CPU' if layer < 25 else 'CUDA0',
                   resident_slots=sl['n_slots'], exposed_wait_union_s=union_us(spans)/1e6,
                   duplicate_eligible_whole_wait_ceiling_s=union_us(eligible)/1e6,
                   evictions=sum(e['kind']=='EVICT' and e['call_id'] in calls for e in events))
        rows.append(row);all_waits += spans;duplicate_waits += eligible
    duration = sum(c['end']['mono_us']-c['begin']['mono_us'] for c in calls.values())/1e6
    tiers = {}
    for tier in ('CPU','CUDA0'):
        group = [r for r in rows if r['tier'] == tier]
        keys = ('observed_logical_bytes','minimum_required_service_bytes',
                'minimum_future_initiation_bytes','repeated_selected_loads',
                'initially_ready_selected_reload_count','loads_not_consumed_in_this_phase')
        tiers[tier] = {k: sum(r[k] for r in group) for k in keys}
    return dict(run=run['id'], scope='slots44 trace-on C-API warm5+148; not slots40 server or cold2044',
                source_hashes=initial['hashes'],
                artifact_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                 (trace,route_path,cap/'before-warm.snap',cap/'after-prefill.snap')},
                prefill_call_s=duration, tiers=tiers, layers=rows,
                exposed_wait_union_s=union_us(all_waits)/1e6,
                duplicate_eligible_wait_ceiling_s=union_us(duplicate_waits)/1e6,
                duplicate_eligible_wait_ceiling_percent=100*union_us(duplicate_waits)/1e6/duration,
                time_class='ESTIMADO conditional whole-barrier ceiling, not a speedup: fixed observed services, zero scheduling/scatter overhead, no contention change',
                first_final_bound='UNKNOWN: corresponding production first-final denominator is not in this trace')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    directories=[repo/'results/c163-instrumentation-overhead-20260930T1145Z',
                 repo/'results/c164-frozen-residency-holdouts-20260930T1155Z']
    checks=[];cases=[]
    for directory in directories:
        checks.append(dict(root=str(directory), **check_manifest(directory)))
        protocol=json.loads((directory/'protocol.json').read_text())
        for run in protocol['runs']:
            if run['id'] in ('c163-on-1','c164-sql','c164-energy'):
                cases.append(case(directory,run))
    with args.output.open('x') as out:
        json.dump(dict(schema='post-c235-prefill-reuse-b1-v1',raw_checks=checks,cases=cases),
                  out,indent=2,allow_nan=False);out.write('\n')
    print(json.dumps([dict(run=c['run'],prefill_s=c['prefill_call_s'],
                          conditional_duplicate_wait_ceiling_percent=c['duplicate_eligible_wait_ceiling_percent'],
                          tiers=c['tiers']) for c in cases]))


if __name__=='__main__':main()
