#!/usr/bin/env python3
"""Measure whether recent exact router sets predict next absent-primary experts."""

import json
from collections import defaultdict
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
from c106_l2_trace_screen import rows, TRACE, SOURCE, EXPERT_BYTES, c105_phase_boundary

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'results/c107-history-prefetch-screen-20260928T2350Z'
HORIZONS=(1,2,4,8)
HISTORICAL_TRACE_SHA='bb3ae9352749283f76ce12b65ea76801916396f87849d609169215fefdf4e40d'
HISTORICAL_COVERAGE=(0,0,0,2)


def decode_route(events):
    boundary=c105_phase_boundary(events)
    selected=defaultdict(set);absent=defaultdict(set)
    token=-1;finished_last=False
    for row in events:
        if row['kind']!='DEMAND' or row['n_tokens']!=1 or row['seq']<boundary:continue
        layer=row['layer']
        if layer==0 and (token<0 or finished_last):
            token+=1;finished_last=False
        if token<0:continue  # masked last-prefill output-layer demand
        key=(token,layer)
        selected[key].add(row['expert'])
        if row['state']==0:absent[key].add(row['expert'])
        if layer==35:finished_last=True
    if token!=31 or set(selected)!={(i,l) for i in range(32) for l in range(36)} or \
       any(len(value)!=4 for value in selected.values()):
        raise GateError('C107 decode segmentation/cardinality invalid')
    return selected,absent


def evaluate(selected,absent,horizon):
    if type(horizon)!=int or horizon<1 or horizon>=32:raise ValueError('bad horizon')
    target_absent=covered=proposed=route_selected=route_covered=0
    for token in range(horizon,32):
        for layer in range(36):
            target=absent[(token,layer)]
            guess=set().union(*(selected[(earlier,layer)]
                                for earlier in range(token-horizon,token)))
            target_absent+=len(target)
            covered+=len(target&guess)
            proposed+=len(guess)
            actual=selected[(token,layer)]
            route_selected+=len(actual)
            route_covered+=len(actual&guess)
    return {'history_tokens':horizon,'evaluated_decode_steps':32-horizon,
            'absent_primary_expert_demands':target_absent,
            'absent_demands_covered':covered,
            'absent_coverage_fraction':covered/target_absent if target_absent else None,
            'proposed_layer_experts':proposed,
            'proposals_targeting_absent_demand_fraction':covered/proposed if proposed else None,
            'selected_layer_experts':route_selected,
            'selected_route_coverage_fraction':route_covered/route_selected,
            'oracle_absent_logical_bytes':target_absent*EXPERT_BYTES,
            'covered_absent_logical_bytes':covered*EXPERT_BYTES}


def historical_status(trace_sha, results):
    """The C107 verdict is a receipt for one observed trace, not a generic gate."""
    coverage=tuple(result['absent_demands_covered'] for result in results)
    if trace_sha==HISTORICAL_TRACE_SHA and coverage==HISTORICAL_COVERAGE and \
       tuple(result['history_tokens'] for result in results)==HORIZONS:
        return 'NO_GO_RECENT_HISTORY_PREFETCH_ON_C105_DECODE'
    return 'ANALYSIS_ONLY_NO_PROSPECTIVE_THRESHOLD'


def main():
    if ROOT.exists():raise GateError('C107 no-replace root exists')
    prior=strict_json((SOURCE/'decision.json').read_text())
    manifest=strict_json((SOURCE/'manifest.json').read_text())
    if prior['status']!='PASS_DIAGNOSTIC_TRACE_NUMERIC_BOUNDARY' or \
       sha256(TRACE)!=manifest['raw_files'][TRACE.name]['sha256']:
        raise GateError('C107 prior trace/decision invalid')
    selected,absent=decode_route(list(rows(TRACE)))
    results=[evaluate(selected,absent,h) for h in HORIZONS]
    trace_sha=sha256(TRACE)
    ROOT.mkdir()
    output={'schema':'c107-history-prefetch-v1','status':historical_status(trace_sha,results),
            'evidence_class':'INFERIDO_FROM_MEASURED_TRACE',
            'trace_sha256':trace_sha,'source_decision_sha256':sha256(SOURCE/'decision.json'),
            'segmentation':'32 decode passes, layers 0..35, four unique DEMAND experts per layer; excluded one final-prefill layer35 n_tokens=1 set',
            'input':'189 prompt plus 32 teacher-forced continuation IDs, not free-generation session',
            'results':results,
            'decision_rule':'Recent-route prefetch merits physical test only if it covers material absent-primary demand with bounded proposals and real lead time; zero/near-zero coverage rejects this simple policy here',
            'limitations':['fixed trace; cache state/prefetch feedback not modeled',
                           'a smart scheduler would avoid I/O for already-resident proposals; proposal count is not wasted physical bytes',
                           'no lead-time, critical-path or quality/sampling claim','does not reject learned/oracle prediction or different workloads'],
            'next_action':'Do not build recent-token expert prefetch for this workload. Investigate bounded overlap with measured waits or another backend mechanism; only revisit prediction with a discriminant that targets novel absent experts.',
            'default_changed':False}
    with (ROOT/'analysis.json').open('x') as out:
        json.dump(output,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    print(json.dumps({'status':output['status'],'coverage':[(x['history_tokens'],x['absent_demands_covered'],x['absent_primary_expert_demands']) for x in results]},allow_nan=False))


if __name__=='__main__':main()
