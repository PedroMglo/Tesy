#!/usr/bin/env python3
"""Three fresh C75 slots32/40 pairs using C120's guarded server entrypoint."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c128_slots40_server as c128


REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = 'c129-slots40-confirm-20260929T1735Z'
ORDER = (('c129-p1-control','control',1),
         ('c129-p1-candidate','candidate',1),
         ('c129-p2-candidate','candidate',2),
         ('c129-p2-control','control',2),
         ('c129-p3-control','control',3),
         ('c129-p3-candidate','candidate',3))


def confirm_policy(root):
    policy = c128.screen_policy(root)
    policy['schema'] = 'c129-slots-confirm-policy-v1'
    policy['pairs'] = 3
    policy['confirm_go'] = ('median paired warm decode duration gain >=8%; '
                            'all three primary gains positive; each protected timing median >=-5%; '
                            'equal work and all identity/output/resource/inventory gates PASS')
    policy.pop('screen_go')
    policy['prior_screen_decision_sha256'] = sha256(REPO/'results/c128-slots40-nominal153-20260929T1710Z/decision.json')
    return policy


def budget(root, remaining):
    prior_path = REPO/'results/c128-slots40-nominal153-20260929T1710Z/epoch-checkpoint.json'
    prior = strict_json(prior_path.read_text())
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat('2026-09-29T13:31:15+00:00') + timedelta(hours=12)
    wall = (deadline-now).total_seconds()
    intervals = []
    for path in sorted((root/'raw').glob('c129-p*-*.receipt.json')):
        if '.start-inventory.' in path.name:
            continue
        row = strict_json(path.read_text())
        a, b = datetime.fromisoformat(row['started_utc']), datetime.fromisoformat(row['ended_utc'])
        if b < a:
            raise GateError('C129 receipt chronology invalid')
        intervals.append({'path':str(path),'seconds':(b-a).total_seconds(),'status':row['status']})
    charged = prior['physical_charged_upper_estimate_s'] + 120 + sum(x['seconds'] for x in intervals)
    physical = 28800-charged
    reserve = remaining*(600+60)+600+7200
    if min(wall,physical) < reserve:
        raise GateError('C129 confirmation plus qualification reserve not admitted')
    return {'schema':'c129-budget-admission-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(prior_path),'completed':intervals,
            'physical_charged_upper_estimate_s':charged,
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall,'remaining_arms':remaining,
            'confirmation_and_qualification_reserve_s':reserve}


def configure():
    c128.configure()
    c128.campaign.ORDER = ORDER
    c128.campaign.ROOT_NAME = ROOT_NAME
    c128.campaign.CAMPAIGN_WRAPPER_FILE = __file__
    c128.campaign.screen_policy = confirm_policy
    c128.campaign.budget = budget


if __name__ == '__main__':
    configure()
    c128.campaign.main()
