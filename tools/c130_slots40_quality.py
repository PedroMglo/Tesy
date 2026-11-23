#!/usr/bin/env python3
"""Original C40 quality12 fixture on confirmed C75 waves ON slots40."""

from datetime import datetime, timezone, timedelta
import os
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c126_wave_quality as campaign


REPO = Path(__file__).resolve().parents[1]
RUN_ID = 'c130-c75-slots40-quality12'
ROOT_NAME = 'c130-slots40-quality-20260929T1800Z'
_make = campaign.make


def make(root):
    protocol, config = _make(root)
    cmd = config['server_command']
    idx = cmd.index('--moe-stream-cache')+1
    if cmd[idx] != '32s' or config['explicit_env'] != {'TESY_CPU_WAVE_SKIP_PARKED':'1'}:
        raise GateError('C130 original C75 quality profile changed')
    cmd[idx] = '40s'
    protocol['identity']['config_sha256'] = campaign.server.digest(config)
    protocol['c126']['numeric_profile'] = {'slots_per_layer':40,
        'backend':'C75','wave_skip_parked':'ON',
        'c129_decision_sha256':sha256(REPO/'results/c129-slots40-confirm-20260929T1735Z/decision.json'),
        'wrapper_sha256':sha256(__file__)}
    return protocol, config


def budget():
    prior_path = REPO/'results/c129-slots40-confirm-20260929T1735Z/epoch-checkpoint.json'
    prior = strict_json(prior_path.read_text())
    now = datetime.now(timezone.utc)
    wall = (datetime.fromisoformat('2026-09-29T13:31:15+00:00')+timedelta(hours=12)-now).total_seconds()
    physical = prior['physical_remaining_lower_bound_s']
    reserve = 6000+60+600+7200
    if min(wall,physical) < reserve:
        raise GateError('C130 quality12 plus future qualification reserve not admitted')
    return {'schema':'c130-budget-admission-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(prior_path),
            'wall_remaining_s':wall,'physical_remaining_lower_bound_s':physical,
            'worst_case_s':reserve,'remaining_future_qualification_reserve_s':7200}


def configure():
    campaign.RUN_ID = RUN_ID
    campaign.ROOT_NAME = ROOT_NAME
    campaign.make = make
    campaign.budget = budget


if __name__ == '__main__':
    configure()
    campaign.main()
