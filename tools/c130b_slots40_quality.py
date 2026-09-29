#!/usr/bin/env python3
"""New quality12 attempt after C130's model-free inventory cadence stop."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c130_slots40_quality as prior


REPO = Path(__file__).resolve().parents[1]
RUN_ID = 'c130b-c75-slots40-quality12'
ROOT_NAME = 'c130b-slots40-quality-20260929T1808Z'
_make = prior.make


def make(root):
    protocol, config = _make(root)
    protocol['c126']['retry_provenance'] = {
        'prior_effective_decision_sha256':sha256(
            REPO/'results/c130-slots40-quality-20260929T1800Z/decision.json'),
        'retry_wrapper_sha256':sha256(__file__),
        'reason':'C130 start-inventory cadence gap before model; original criteria retained'}
    return protocol, config


def budget():
    prior_path = REPO/'results/c129-slots40-confirm-20260929T1735Z/epoch-checkpoint.json'
    prior_checkpoint = strict_json(prior_path.read_text())
    now = datetime.now(timezone.utc)
    wall = (datetime.fromisoformat('2026-09-29T13:31:15+00:00')+
            timedelta(hours=12)-now).total_seconds()
    # C130's only live unit ended before model launch after ~53 s. Charge a
    # conservative 120 s for its entire preparation/scope/failure envelope.
    physical = prior_checkpoint['physical_remaining_lower_bound_s']-120
    reserve = 6000+60+600+7200
    if min(wall,physical) < reserve:
        raise GateError('C130b quality12 plus future qualification reserve not admitted')
    return {'schema':'c130b-budget-admission-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(prior_path),
            'c130_failed_live_upper_s':120,
            'wall_remaining_s':wall,'physical_remaining_lower_bound_s':physical,
            'worst_case_s':reserve,'remaining_future_qualification_reserve_s':7200}


def configure():
    prior.configure()
    prior.campaign.RUN_ID = RUN_ID
    prior.campaign.ROOT_NAME = ROOT_NAME
    prior.campaign.make = make
    prior.campaign.budget = budget


if __name__ == '__main__':
    configure()
    prior.campaign.main()
