#!/usr/bin/env python3
"""No-replace C105 raw reanalysis; historical C106/C107 files stay immutable."""

import argparse
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c84_trace_validate import validate, EXPERT_BYTES
from c106_l2_trace_screen import (TRACE, SOURCE, BUDGETS, REPO, rows,
                                  layer_destinations, c105_phase_boundary,
                                  simulate, wait_summary)
from c107_history_prefetch_screen import (decode_route, evaluate, HORIZONS,
                                           historical_status)
from c108_epoch_ledger import build as build_ledger
from datetime import datetime, timezone
from run_bounded import sha256

OLD_C106 = REPO / 'results/c106-l2-fixed-trace-screen-20260928T2340Z/analysis.json'
OLD_C107 = REPO / 'results/c107-history-prefetch-screen-20260928T2350Z/analysis.json'


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def build():
    manifest = strict_json((SOURCE / 'manifest.json').read_text())
    source_decision = strict_json((SOURCE / 'decision.json').read_text())
    trace_sha = sha256(TRACE)
    if trace_sha != manifest['raw_files'][TRACE.name]['sha256'] or \
       source_decision['status'] != 'PASS_DIAGNOSTIC_TRACE_NUMERIC_BOUNDARY':
        raise GateError('C108 C105 provenance invalid')
    receipt = validate(TRACE)
    events = list(rows(TRACE))
    destinations = layer_destinations(TRACE)
    if any(destinations[layer] != ('CPU' if layer < 25 else 'GPU') for layer in range(36)):
        raise GateError('C108 C105 P12 placement invalid')
    boundary = c105_phase_boundary(events)
    phase_of = lambda row: 'prefill' if row['seq'] < boundary else 'decode'
    waits = wait_summary(events, phase_of)
    scenarios = []
    for budget in BUDGETS:
        for mode in ('on_load_lru', 'on_evict_lru'):
            counts = simulate(events, budget//EXPERT_BYTES, mode,
                              destinations=destinations, phase_of=phase_of)
            misses = sum(value['misses'] for value in counts.values())
            saved = sum(value['saved'] for value in counts.values())
            scenarios.append({'budget_bytes': budget, 'mode': mode,
                              'misses': misses, 'saved': saved,
                              'saved_fraction': saved/misses if misses else None,
                              'phase_destination': {f'{phase}:{destination}': dict(value)
                                                    for (phase, destination), value in sorted(counts.items())}})
    old_c106 = strict_json(OLD_C106.read_text())
    old_counts = {(row['budget_bytes'], row['mode']):
                  (row['total_demand_misses'], row['total_saved_demand_misses'])
                  for row in old_c106['scenarios']}
    if any(old_counts[(row['budget_bytes'], row['mode'])] !=
           (row['misses'], row['saved']) for row in scenarios):
        raise GateError('C108 global C106 savings changed; investigation needed')
    selected, absent = decode_route(events)
    prefetch = [evaluate(selected, absent, horizon) for horizon in HORIZONS]
    if historical_status(trace_sha, prefetch) != \
       'NO_GO_RECENT_HISTORY_PREFETCH_ON_C105_DECODE':
        raise GateError('C108 C107 historical observation changed')
    return {'schema': 'c108-trace-errata-v1', 'status': 'REANALYSIS_VALIDATED_FIXED_TRACE',
            'evidence_class': 'REPRODUZIDO_MODEL_FREE_FROM_MEASURED_TRACE',
            'trace_sha256': trace_sha, 'c105_manifest_sha256': sha256(SOURCE / 'manifest.json'),
            'historical_c106_sha256': sha256(OLD_C106),
            'historical_c107_sha256': sha256(OLD_C107),
            'trace_validation': {key: value for key, value in receipt.items() if key != 'layers'},
            'placement': destinations, 'first_decode_event_seq': boundary,
            'single_token_prefill_demand_count': 4,
            'waits_diagnostic_not_total_removable': waits,
            'scenarios': scenarios,
            'global_state0_and_savings_unchanged': True,
            'c107_historical_status': historical_status(trace_sha, prefetch),
            'c107_coverage': [{'horizon': row['history_tokens'],
                               'covered': row['absent_demands_covered'],
                               'absent': row['absent_primary_expert_demands']}
                              for row in prefetch],
            'corrections': ['state=1 is LOADING/in-flight; state=2 is RESIDENT',
                            'four layer-35 n_tokens=1 DEMAND events belong to final prefill',
                            'phase boundary is verified by 32 ordered decode passes',
                            'destination follows C105 loader header, not layer>=25 in generic code',
                            'LOAD_END now needs its matching LOAD_BEGIN; C107 verdict is trace-bound'],
            'limits': ['trace only 189+32, not warm nominal128/153 session',
                       'LOAD spans include read and tensor_set; WAIT spans omit other blocking',
                       'fixed routed stream cannot measure cache feedback or equal-memory pool alternative',
                       'no new model inference or performance promotion']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.root.exists():
        raise GateError('C108 no-replace root exists')
    result = build()
    ledger = build_ledger(datetime.now(timezone.utc))
    args.root.mkdir()
    write(args.root / 'analysis.json', result)
    write(args.root / 'epoch-ledger.json', ledger)
    write(args.root / 'budget-admission.json', {
        'schema': 'c108-budget-admission-v1',
        'status': 'MODEL_FREE_REANALYSIS_COMPLETE_PHYSICAL_NOT_YET_ADMITTED',
        'wall_remaining_s_no_pause_discount': ledger['wall_remaining_s_no_pause_discount'],
        'physical_remaining_lower_bound_s': ledger['physical_remaining_lower_bound_s'],
        'closure_reserve_s': 600,
        'next_physical_worst_case_s': 9*450+900+600,
        'note': 'Epoch ledger gives conservative administrative room only; live host, identity, scope, raw-space and model-free probe gates still required.'})
    write(args.root / 'manifest.json', {
        'schema': 'c108-manifest-v1', 'trace_sha256': result['trace_sha256'],
        'analysis_sha256': sha256(args.root / 'analysis.json'),
        'epoch_ledger_sha256': sha256(args.root / 'epoch-ledger.json'),
        'budget_admission_sha256': sha256(args.root / 'budget-admission.json'),
        'historical_files_untouched': True})
    print(json.dumps({'status': result['status'], 'trace_events': result['trace_validation']['events'],
                      'wall_remaining_s': ledger['wall_remaining_s_no_pause_discount'],
                      'physical_remaining_lower_bound_s': ledger['physical_remaining_lower_bound_s']}))


if __name__ == '__main__':
    main()
