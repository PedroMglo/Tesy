#!/usr/bin/env python3
"""Reconcile the existing C55-C107 epoch without treating missing durations as zero."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EPOCH_START_CONSERVATIVE = datetime.fromisoformat('2026-09-28T12:00:00+00:00')
LAST_PHYSICAL_END = datetime.fromisoformat('2026-09-28T23:39:03.547396+00:00')
PAUSE_START_BOUND = datetime.fromisoformat('2026-09-29T00:00:00+00:00')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def unit(path):
    decision = path / 'decision.json'
    status = load(decision).get('status', 'STATUS_NOT_RECORDED') if decision.exists() else 'STATUS_NOT_RECORDED'
    records = []
    runs = path / 'runs.jsonl'
    if runs.exists():
        for line in runs.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            elapsed = row.get('elapsed_s')
            evidence = str(runs.relative_to(REPO))
            if elapsed is None and row.get('raw_path'):
                raw = REPO / row['raw_path']
                if raw.is_file():
                    elapsed = load(raw).get('elapsed_s')
                    evidence = str(raw.relative_to(REPO))
            records.append({'run_id': row.get('run_id'), 'elapsed_s': elapsed,
                            'evidence': evidence, 'sha256': digest(REPO / evidence)})
    known = [row['elapsed_s'] for row in records if type(row['elapsed_s']) in (int, float)]
    summary = load(decision) if decision.exists() else {}
    reported = summary.get('budget_consumed', {}).get('model_process_elapsed_s')
    if type(reported) in (int, float):
        observed = reported
        authority = 'decision.budget_consumed.model_process_elapsed_s'
    elif records and len(known) == len(records):
        observed = sum(known)
        authority = 'runs.jsonl plus linked raw elapsed_s'
    else:
        observed = None
        authority = 'INCOMPLETE_PROCESS_ELAPSED'
    return {'unit': path.name, 'status': status, 'run_count': len(records),
            'runs': records, 'observed_process_elapsed_s': observed,
            'duration_authority': authority,
            'decision_sha256': digest(decision) if decision.exists() else None}


def build(now):
    results = REPO / 'results'
    paths = sorted(path for path in results.glob('c*-20260928T*Z')
                   if path.is_dir() and path.name.rsplit('-20260928T', 1)[-1][:4] >= '1200')
    units = [unit(path) for path in paths]
    known = sum(row['observed_process_elapsed_s'] for row in units
                if row['observed_process_elapsed_s'] is not None)
    physical_upper = (LAST_PHYSICAL_END-EPOCH_START_CONSERVATIVE).total_seconds()
    wall_elapsed = (now-EPOCH_START_CONSERVATIVE).total_seconds()
    return {'schema': 'c108-epoch-ledger-v1', 'evidence_class': 'MIXED_MEASURED_AND_CONSERVATIVE_BOUND',
            'epoch_start_conservative_utc': EPOCH_START_CONSERVATIVE.isoformat(),
            'epoch_start_basis': 'earlier than the C55 timestamp and first continuation commits; deliberately conservative, not a measured start',
            'last_physical_end_utc': LAST_PHYSICAL_END.isoformat(),
            'last_physical_end_receipt': 'results/c105-c84-8k-trace-boundary-20260928T2335Z/raw/c105-c84-trace-on01.json',
            'owner_pause': {'classification': 'REQUESTED_BY_OWNER',
                            'start_bound_utc': PAUSE_START_BOUND.isoformat(),
                            'physical_model_process_during_pause': 'NONE_OBSERVED_AT_RESUME',
                            'wall_budget_discount_s': 0},
            'now_utc': now.isoformat(), 'units': units,
            'known_reported_process_elapsed_s': known,
            'known_reported_process_elapsed_is_complete': False,
            'physical_elapsed_upper_bound_s': physical_upper,
            'physical_upper_bound_method': 'all wall time from conservative epoch start through last recorded model process end; includes preflights, idle, diagnostics and all gaps before pause',
            'physical_remaining_lower_bound_s': max(0, 16*3600-physical_upper),
            'wall_elapsed_s_no_pause_discount': wall_elapsed,
            'wall_remaining_s_no_pause_discount': max(0, 24*3600-wall_elapsed),
            'limits_s': {'wall': 24*3600, 'physical': 16*3600},
            'limitations': ['Some older units have no per-process elapsed in compact runs; their time is covered by the conservative wall upper bound',
                            'Owner pause is counted against the wall budget; physical upper bound ends at the last model run',
                            'No new physical unit may start without a live inventory and sufficient closure reserve']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    result = build(now)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in
                      ('known_reported_process_elapsed_s', 'physical_elapsed_upper_bound_s',
                       'physical_remaining_lower_bound_s', 'wall_remaining_s_no_pause_discount')}))


if __name__ == '__main__':
    main()
