#!/usr/bin/env python3
"""Three fresh nominal153 server pairs using the C120 guarded entrypoint."""

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from c2_gate import GateError, strict_json
import c120_nominal_server as campaign

REPO = Path(__file__).resolve().parents[1]

campaign.ORDER = (
    ('c124-p1-control', 'control', 1),
    ('c124-p1-candidate', 'candidate', 1),
    ('c124-p2-candidate', 'candidate', 2),
    ('c124-p2-control', 'control', 2),
    ('c124-p3-control', 'control', 3),
    ('c124-p3-candidate', 'candidate', 3),
)
campaign.ROOT_NAME = 'c124-nominal153-confirm-20260929T1515Z'
campaign.CAMPAIGN_WRAPPER_FILE = __file__
_screen_policy = campaign.screen_policy


def confirm_policy(root):
    policy = _screen_policy(root)
    policy['schema'] = 'c124-confirm-policy-v1'
    policy['pairs'] = 3
    policy['primary'] = 'warm first_final_content_s'
    policy['confirm_go'] = ('median paired primary >=8%; all three primary gains positive; '
                            'all four protected timing medians >=-5%; all other gates PASS')
    policy.pop('screen_go')
    return policy


def charged_intervals(root):
    paths = []
    paths.extend(sorted(p for p in (REPO / 'results/c121-nominal153-20260929T1350Z/raw').glob('c121-p*.receipt.json')
                        if '.start-inventory.' not in p.name))
    paths.append(REPO / 'results/c123-warm153-decode-trace-20260929T1450Z/raw/c123-c75-warm153.receipt.json')
    paths.extend(sorted(p for p in (root / 'raw').glob('c124-p*.receipt.json')
                        if '.start-inventory.' not in p.name))
    intervals = []
    for path in paths:
        row = strict_json(path.read_text())
        a = datetime.fromisoformat(row['started_utc']); b = datetime.fromisoformat(row['ended_utc'])
        if b < a:
            raise GateError('C124 physical receipt chronology invalid')
        intervals.append({'receipt': str(path), 'duration_s': (b-a).total_seconds(),
                          'status': row['status']})
    for path in ('results/c122-warm153-decode-trace-20260929T1433Z/raw/c122-numeric-canary-on01.json',
                 'results/c123-warm153-decode-trace-20260929T1450Z/raw/c123-numeric-canary-on01.json'):
        row = strict_json((REPO / path).read_text())
        a = datetime.fromisoformat(row['started_utc']); b = datetime.fromisoformat(row['ended_utc'])
        intervals.append({'receipt': path, 'duration_s': (b-a).total_seconds(),
                          'status': 'CANARY_RETURN_'+str(row['returncode'])})
    return intervals


def epoch_budget(root, remaining):
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(campaign.EPOCH_START_UTC)
    wall = (start + timedelta(seconds=campaign.EPOCH_WALL_S) - now).total_seconds()
    intervals = charged_intervals(root)
    measured_live_s = sum(row['duration_s'] for row in intervals)
    # C120/C121/C122/C123 inventories, smokes and preflight work outside
    # these receipts are charged conservatively by a 1200 s live allowance.
    # This is an admission upper estimate, separate from model-active time.
    allowance_s = 1200.0
    charged_s = measured_live_s + allowance_s
    physical = campaign.EPOCH_PHYSICAL_S - charged_s
    reserve = remaining * (600 + 60) + 600
    if min(wall, physical) < reserve:
        raise GateError('C124 epoch cannot admit remaining arms and closure')
    return {'schema':'c124-budget-admission-v1','utc':now.isoformat(),
            'remaining_arms':remaining,'wall_remaining_s':wall,
            'physical_remaining_lower_bound_s':physical,'worst_case_s':reserve,
            'measured_live_intervals_s':measured_live_s,
            'unreceipted_live_allowance_s':allowance_s,
            'physical_charged_upper_estimate_s':charged_s,
            'intervals':intervals,'method':'unique receipts plus explicit live allowance; model-free analysis excluded'}


campaign.screen_policy = confirm_policy
campaign.budget = epoch_budget


if __name__ == '__main__':
    campaign.main()
