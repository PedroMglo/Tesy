#!/usr/bin/env python3
"""C36c identity with a prospective 128-ID increment fixture."""

import sys
from pathlib import Path

import c36_prefix4096 as base
from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT=Path('results/c36c-prefix4096-20260928T0203Z')
PARENT=Path('results/c36b-prefix4096-20260928T0155Z/decision.json')
SPEC=(('c36c-prefix4096-bridge','on','G1',1),)
REQUESTS=('c36c-prefix4096','c36c-increment128')
ORIGINAL_FROZEN=base.frozen


def frozen(root,spec):
    high=strict_json((root/'protocol.json').read_text())
    if root!=ROOT or high['campaign_identity']!='C36c' or \
            high['parent_c36b_failure_sha256']!=sha256(PARENT) or \
            strict_json(PARENT.read_text())['status']!='FAIL_HARNESS_TOKEN_RELATION_NO_REQUEST':
        raise GateError('C36c parent/root identity changed')
    protocol,config,tasks,row=ORIGINAL_FROZEN(root,spec)
    protocol['campaign_id']='tesy-c36c-prefix4096-20260928'
    protocol['protocol_id']=spec[0]+'-v1'
    protocol['c36c']=protocol.pop('c36')
    protocol['c36c']['runner_sha256']=sha256(__file__)
    protocol['c36c']['parent_c36b_failure_sha256']=sha256(PARENT)
    protocol['c36c']['input_note']='127 beta words hypothesized to yield 128 prompt IDs'
    return protocol,config,tasks,row


def main():
    base.ROOT=ROOT
    base.SPEC=SPEC
    base.REQUESTS=REQUESTS
    base.frozen=frozen
    return base.main()


if __name__=='__main__':
    sys.exit(main())
