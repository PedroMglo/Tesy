#!/usr/bin/env python3
"""C75 wave ON slots32/40 nominal153 screen via C120's guarded entrypoint."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c112_nominal_session_base as base
import c120_nominal_server as campaign


REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = 'c128-slots40-nominal153-20260929T1710Z'
ORDER = (('c128-p1-control','control',1),
         ('c128-p1-candidate','candidate',1),
         ('c128-p2-candidate','candidate',2),
         ('c128-p2-control','control',2))
BACKEND = (Path('/tmp/tesy-c75-backend-20260928'), 'build-c75-cuda',
           '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5',
           {'TESY_CPU_WAVE_SKIP_PARKED':'1'})

_base_make = base.make
_campaign_make = campaign.make


def slot_make(root, arm):
    protocol, config = _base_make(root, arm)
    command = config['server_command']
    i = command.index('--moe-stream-cache') + 1
    if command[i] != '32s':
        raise GateError('C128 C75 baseline slot command changed')
    if arm == 'candidate':
        command[i] = '40s'
    protocol['identity']['config_sha256'] = campaign.server.digest(config)
    return protocol, config


base.make = slot_make


def make(root, spec):
    protocol, config = _campaign_make(root, spec)
    arm = spec[1]
    protocol['c120']['c128_numeric_profile'] = {
        'backend':'C75', 'wave_skip_parked':'ON',
        'slots_per_layer':32 if arm == 'control' else 40,
        'slots40_numeric_decision_sha256':sha256(REPO/'results/c127-slots40-numeric-20260929T1654Z/decision.json'),
        'claim':'new profile screen, not same-profile cache-only comparison'}
    return protocol, config


def screen_policy(root):
    policy = campaign_screen_policy(root)
    policy.update(schema='c128-slots-screen-policy-v1',
                  objective='C75 ON slots40 versus C75 ON slots32 on nominal153',
                  primary='warm decode_s',
                  protected=['warm first_final_content_s','warm prefill_s',
                             'cold decode_s','cold first_final_content_s',
                             'cold prefill_s','answer/prefix/resources/identity/inventory'],
                  screen_go=('median paired warm decode duration gain >=8%; both pairs positive; '
                             'each protected timing median >=-5%; all other gates PASS'),
                  profiles={'control':{'backend':'C75','wave':'ON','slots':32},
                            'candidate':{'backend':'C75','wave':'ON','slots':40}},
                  numerical_provenance='C127 189+32 boundary and 36 resident FFN layers; full 8K independent NOT_RUN',
                  physical_reserve_after_screen_s=7200)
    return policy


def budget(root, remaining):
    prior_path = REPO/'results/c127-slots40-numeric-20260929T1654Z/epoch-checkpoint.json'
    prior = strict_json(prior_path.read_text())
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(prior['epoch_start_utc']) + timedelta(hours=12)
    wall = (deadline-now).total_seconds()
    prefix = ORDER[0][0].split('-p',1)[0]
    intervals = []
    for path in sorted((root/'raw').glob(f'{prefix}-p*-*.receipt.json')):
        if '.start-inventory.' in path.name:
            continue
        row = strict_json(path.read_text())
        a, b = datetime.fromisoformat(row['started_utc']), datetime.fromisoformat(row['ended_utc'])
        if b < a:
            raise GateError('C128 receipt chronology invalid')
        intervals.append({'path':str(path), 'seconds':(b-a).total_seconds(), 'status':row['status']})
    # Allowance includes the fresh c55 inventory and non-model live checks.
    charged = prior['physical_charged_upper_estimate_s'] + 120 + sum(x['seconds'] for x in intervals)
    physical = 28800 - charged
    reserve = remaining*(600+60) + 600 + 7200
    if min(wall,physical) < reserve:
        raise GateError('C128 screen plus qualification reserve not admitted')
    return {'schema':'c128-budget-admission-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(prior_path), 'completed':intervals,
            'physical_charged_upper_estimate_s':charged,
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall, 'remaining_arms':remaining,
            'screen_and_qualification_reserve_s':reserve}


campaign_screen_policy = campaign.screen_policy


def configure():
    """Set this campaign's process-local C120 configuration at the entrypoint."""
    base.BACKENDS = {'control':BACKEND, 'candidate':BACKEND}
    base.make = slot_make
    campaign.ORDER = ORDER
    campaign.ROOT_NAME = ROOT_NAME
    campaign.CAMPAIGN_WRAPPER_FILE = __file__
    campaign.make = make
    campaign.screen_policy = screen_policy
    campaign.budget = budget


if __name__ == '__main__':
    configure()
    campaign.main()
