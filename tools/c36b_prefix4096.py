#!/usr/bin/env python3
"""C36b identity after the C36 preflight schema error."""

import sys
from pathlib import Path

import c36_prefix4096 as base
from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT=Path('results/c36b-prefix4096-20260928T0155Z')
PARENT=Path('results/c36-prefix4096-20260928T0153Z/decision.json')
SPEC=(('c36b-prefix4096-bridge','on','G1',1),)
REQUESTS=('c36b-prefix4096','c36b-increment128')
ORIGINAL_FROZEN=base.frozen


def frozen(root,spec):
    high=strict_json((root/'protocol.json').read_text())
    if root!=ROOT or high['campaign_identity']!='C36b' or \
            high['parent_c36_failure_sha256']!=sha256(PARENT) or \
            strict_json(PARENT.read_text())['status']!='FAIL_HARNESS_PREFLIGHT_PROTOCOL_KEY_NO_MODEL':
        raise GateError('C36b parent/root identity changed')
    protocol,config,tasks,row=ORIGINAL_FROZEN(root,spec)
    protocol['campaign_id']='tesy-c36b-prefix4096-20260928'
    protocol['protocol_id']=spec[0]+'-v1'
    protocol['c36b']=protocol.pop('c36')
    protocol['c36b']['runner_sha256']=sha256(__file__)
    protocol['c36b']['parent_c36_failure_sha256']=sha256(PARENT)
    return protocol,config,tasks,row


def main():
    base.ROOT=ROOT
    base.SPEC=SPEC
    base.REQUESTS=REQUESTS
    base.frozen=frozen
    return base.main()


if __name__=='__main__':
    sys.exit(main())
