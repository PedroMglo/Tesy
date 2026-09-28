#!/usr/bin/env python3
"""Prospective C15 original/plain/profile diagnostic after the C42 latency result."""

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import c18_cpu_telemetry as telemetry
import c34b_wave_profile as base
from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c43-wave-critical-20260928T0809Z')
SPECS = (('c43-control-cold513', base.ORIGINAL, 'CONTROL', 1),
         ('c43-c15-plain-cold513', base.DIAGNOSTIC, 'C15_PLAIN', 2),
         ('c43-c15-profile-cold513', base.DIAGNOSTIC, 'C15_PROFILE', 3))
TOKEN_SHA = 'bc41ccff712f8f8e1984f374051135e315e346641c060beba985ae983e162ee0'
PARENT = Path('results/c42-8k-boundary-20260928T0741Z/decision.json')
ORIGINAL_FROZEN = base.frozen


def overall(root):
    row = strict_json((root / 'protocol.json').read_text())
    if row['schema'] != 'c43-wave-critical-protocol-v1' or \
       row['parent_c42_decision_sha256'] != sha256(PARENT) or \
       row['c33_decision_sha256'] != sha256('results/c33-wave-tracer-feasibility-20260928T0034Z/decision.json') or \
       row['input_sha256'] != sha256(root / 'input.json') or \
       row['usage_contract_sha256'] != sha256(root / 'usage-contract.json') or \
       row['runner_sha256'] != sha256(__file__) or \
       row['cpu_telemetry_sha256'] != sha256(telemetry.__file__) or \
       row['official_prompt_ids_sha256'] != TOKEN_SHA or \
       dt.datetime.now(ZoneInfo('Europe/Lisbon')).date().isoformat() != row['template_local_date']:
        raise GateError('C43 source/date/input/parent freeze differs')
    if strict_json(PARENT.read_text())['status'] != 'PASS_BOUNDARY_RETRIEVAL_TESTED_SCOPE':
        raise GateError('C43 parent C42 result missing')
    return row


def frozen(root, spec):
    protocol, config, tasks = ORIGINAL_FROZEN(root, spec)
    top = overall(root)
    protocol['campaign_id'] = 'tesy-c43-wave-critical-20260928'
    protocol['c43'] = {'runner_sha256': sha256(__file__),
                       'cpu_telemetry_sha256': sha256(telemetry.__file__),
                       'parent_c42_decision_sha256': sha256(PARENT),
                       'local_template_date': top['template_local_date'],
                       'optimistic_bound_policy': top['bound_rule']}
    return protocol, config, tasks


def physical_budget(root):
    idle = sum(strict_json(path.read_text())['duration_s']
               for path in Path('results').glob('c*-*/**/*-idle.json'))
    completed = sum((root / f'{spec[0]}-receipt.json').exists() for spec in SPECS)
    remaining = len(SPECS) - completed
    if program_physical_consumed() + idle + 2400 + remaining*(900+300+90) + 300 > 16*3600:
        raise GateError('C43 remaining physical budget cannot cover all frozen arms and cleanup')


def main():
    base.ROOT = ROOT
    base.SPECS = SPECS
    base.BY_ID = {row[0]: row for row in SPECS}
    base.TOKEN_SHA = TOKEN_SHA
    base.overall = overall
    base.frozen = frozen
    base.physical_budget = physical_budget
    return base.main()


if __name__ == '__main__':
    main()
