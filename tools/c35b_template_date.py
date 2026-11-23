#!/usr/bin/env python3
"""C35b identity after the C35 prelaunch scope failure."""

import sys
from pathlib import Path

import c35_template_date as base
from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path('results/c35b-template-date-20260928T0122Z')
PARENT = Path('results/c35-template-date-20260928T0115Z/decision.json')
SPECS = (('c35b-date-shift-control', 'shifted', 'G1', 1),
         ('c35b-date-stable-candidate', 'stable', 'G2', 2))
REQUESTS = ('c35b-first-turn2048', 'c35b-second-turn128')
ORIGINAL_FROZEN = base.frozen


def frozen(root, spec):
    if root != ROOT or strict_json(PARENT.read_text())['status'] != \
            'FAIL_HARNESS_PRELAUNCH_SCOPE_NO_MODEL':
        raise GateError('C35b parent/root identity changed')
    top = strict_json((root/'protocol.json').read_text())
    if top['parent_c35_failure_sha256'] != sha256(PARENT) or \
            top['campaign_identity'] != 'C35b':
        raise GateError('C35b parent receipt changed')
    protocol, config, tasks, workload = ORIGINAL_FROZEN(root, spec)
    protocol['campaign_id'] = 'tesy-c35b-template-date-20260928'
    protocol['protocol_id'] = spec[0]+'-v1'
    protocol['c35b'] = protocol.pop('c35')
    protocol['c35b']['runner_sha256'] = sha256(__file__)
    protocol['c35b']['parent_c35_failure_sha256'] = sha256(PARENT)
    return protocol, config, tasks, workload


def main():
    base.ROOT = ROOT
    base.SPECS = SPECS
    base.REQUESTS = REQUESTS
    base.BY_ID = {row[0]:row for row in SPECS}
    base.frozen = frozen
    return base.main()


if __name__ == '__main__':
    sys.exit(main())
