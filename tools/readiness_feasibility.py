"""Offline readiness envelopes. Observed services remain fixed; no speedup claim."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from c122_trace_validate import union_us
from c152_journal_validate import validate
from c152_snapshot_read import snapshot
from residency_capture_gate import plan
from residency_overhead_analyze import phases


def check_manifest(directory, name='raw-manifest.json'):
    manifest = json.loads((directory / name).read_text())
    checked = 0
    for key, expected in manifest['files'].items():
        path = directory / key if key.startswith('raw/') else directory / 'raw' / key
        data = path.read_bytes()
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('immutable raw changed: ' + str(path))
        checked += len(data)
    return {'files': len(manifest['files']), 'bytes': checked,
            'manifest_sha256': hashlib.sha256((directory / name).read_bytes()).hexdigest()}


def optimistic_overlap(releases, work_us, ready_us, start_us):
    """Preemptive work relaxed across experts, release-constrained capacity.

    All four equally sized experts, no reordering/reduction implementation claim.
    Gives an optimistic amount of first-op/full-FFN work executable before ready.
    """
    if len(releases) != 4 or work_us < 0 or ready_us < start_us:
        raise ValueError('invalid fixed decode scope')
    if any(r > ready_us for r in releases):
        raise ValueError('release after all-ready')
    per_expert = work_us / 4
    executed = 0.0
    previous = start_us
    available = 0
    for timestamp in sorted(set(max(start_us, r) for r in releases)) + [ready_us]:
        timestamp = min(timestamp, ready_us)
        executed += min(max(0, timestamp - previous), max(0, available * per_expert - executed))
        available = sum(max(start_us, r) <= timestamp for r in releases)
        previous = timestamp
    return min(executed, work_us, ready_us-start_us)


def ordered_gain(releases, slots, work_us, start_us, wait_end_us):
    """Fixed ascending-slot MMID schedule; equal per-expert service is conditional."""
    if len(releases)!=4 or len(slots)!=4 or len(set(slots))!=4 or work_us<0:
        raise ValueError('invalid ordered four-expert MMID')
    finish = start_us
    for slot, release in sorted(zip(slots, releases)):
        finish = max(finish, release) + work_us / len(releases)
    return max(0, wait_end_us + work_us - finish)


def journal_case(directory, run):
    capture = Path(run['command'][-1])
    trace = Path(run['env']['TESY_C84_EXPERT_TRACE_FILE'] + '.window.trace')
    parsed = validate(trace, initial=snapshot(capture/'before-warm.snap'))
    grouped = defaultdict(list)
    for event in parsed['rows']:
        grouped[(event['call_id'], event['layer'])].append(event)
    barriers = {(b['begin']['call_id'], b['begin']['layer']): b for b in parsed['barriers']
                if b['begin']['call_id'] >= 11}
    table = []
    for call in range(11, 58):
        for layer in range(36):
            events = grouped[(call, layer)]
            remaps = [e for e in events if e['kind'] == 'REMAP_DONE']
            if len(remaps) != 1:
                raise ValueError('decode must have one remap per layer/call')
            remap = remaps[0]
            demands = [e for e in events if e['kind'] == 'DEMAND']
            if len(demands) != 4 or len({e['expert'] for e in demands}) != 4:
                raise ValueError('four authoritative decode experts required')
            start = next(e['mono_us'] for e in events if e['kind'] == 'MUTEX_WAIT_END')
            next_events = grouped[(call, layer+1)] if layer < 35 else []
            next_start = next((e['mono_us'] for e in next_events if e['kind'] == 'MUTEX_WAIT_BEGIN'),
                              parsed['calls'][call]['end']['mono_us'])
            b = barriers.get((call, layer))
            if b:
                groups = b['demands']; commits = {(e['slot'],e['generation']): e['mono_us']
                                                for e in b['blocking_commits']}
                releases = [b['begin']['mono_us'] if e['state'] == 2 else
                            commits[(e['slot'],e['generation'])] for e in groups]
                begin, end, ready = b['begin']['mono_us'], b['end']['mono_us'], b['ready_us']
                slots = [e['slot'] for e in groups]
            else:
                begin = end = ready = remap['mono_us']; releases = [ready]*4
                slots = [e['slot'] for e in demands]
            table.append({'call': call, 'layer': layer, 'tier': 'CPU' if layer < 25 else 'CUDA0',
                'router_known_by_us': start, 'router_timestamp_kind': 'MUTEX_WAIT_END latest bound, not exact router completion',
                'experts': [e['expert'] for e in demands], 'slots': slots,
                'misses': sum(e['state'] != 2 for e in demands),
                'release_us': releases, 'wait_begin_us': begin, 'wait_end_us': end,
                'all_ready_us': ready, 'wake_tail_us': end-ready,
                'wait_us': end-begin, 'service_window_us': ready-begin,
                'remap_done_us': remap['mono_us'],
                'following_router_gap_us': max(0, next_start-remap['mono_us']),
                'compute_gap_class': 'Gross upper estimate includes attention/router/other unshiftable work, not first MMID'})
    decode = phases(plan(capture))['decode']
    cpu = [r for r in table if r['tier'] == 'CPU']
    waits = union_us((r['wait_begin_us'],r['wait_end_us']) for r in cpu)
    gross = sum(min(r['service_window_us'], r['following_router_gap_us'])+r['wake_tail_us'] for r in cpu)
    return {'run': run['id'], 'scope': 'slots44 trace-on direct C API decode47, not slots40 server or C142',
        'trace_sha256': hashlib.sha256(trace.read_bytes()).hexdigest(),
        'decode_s': decode, 'cpu_wait_union_s': waits/1e6,
        'gross_gap_envelope_percent': 100*gross/1e6/decode,
        'first_MMID_compute': 'UNKNOWN_PENDING_OPERATOR_TIMING', 'rows': table}


def measured_envelope(case, first_us, full_us):
    rows = [r for r in case['rows'] if r['tier'] == 'CPU']
    result = {}
    for name, work in [('first_MMID',first_us), ('full_FFN',full_us)]:
        service = sum(optimistic_overlap(r['release_us'],work,r['all_ready_us'],r['wait_begin_us']) for r in rows)
        wake = sum(r['wake_tail_us'] for r in rows)
        ordered = sum(ordered_gain(r['release_us'],r['slots'],work,r['wait_begin_us'],r['wait_end_us']) for r in rows)
        coarse = sum(min(r['service_window_us'],work) for r in rows)
        result[name] = {'optimistic_service_overlap_s': service/1e6, 'separate_wake_tail_s': wake/1e6,
            'conditional_percent_including_wake': 100*(service+wake)/1e6/case['decode_s'],
            'coarse_total_work_bound_percent_including_wake':100*(coarse+wake)/1e6/case['decode_s'],
            'ascending_slot_equal_service_scenario_percent': 100*ordered/1e6/case['decode_s'],
            'assumptions': 'Uniform expert service, fixed observed commits, no added contention; work is isolated measured range, not rigorous production bound'}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('output',type=Path); args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    roots=[repo/'results/c163-instrumentation-overhead-20260930T1145Z',
           repo/'results/c164-frozen-residency-holdouts-20260930T1155Z']
    cases=[]; checks=[]
    for directory in roots:
        checks.append({'root':str(directory),**check_manifest(directory)})
        protocol=json.loads((directory/'protocol.json').read_text())
        for run in protocol['runs']:
            if run['id'] in ('c163-on-1','c164-sql','c164-energy'):
                cases.append(journal_case(directory,run))
    with args.output.open('x') as out:
        json.dump({'evidence_class':'TEMPORAL_BOUND_CONDITIONAL','raw_checks':checks,'cases':cases},out,indent=2,allow_nan=False);out.write('\n')
