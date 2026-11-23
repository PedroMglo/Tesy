#!/usr/bin/env python3
"""C133: one prospective session retry after C132 output cap and raw gap."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import c132_diverse_session as parent
from c2_gate import GateError, strict_json
from run_bounded import sha256


REPO=Path(__file__).resolve().parents[1]
ROOT_NAME='c133-diverse-active-session-20260929T2000Z'
RUN_ID='c133-c75-slots40-diverse20'
WORKLOAD=REPO/'workloads/c133_diverse_session.json'
_make=parent.make


def make(root):
    protocol,config=_make(root)
    config['request_policy']['max_tokens']=768
    config['require_natural_stop']=True
    config['total_timeout_s']=6300
    protocol['schema_version']='c133-protocol-v1'
    protocol['identity']['config_sha256']=parent.server.digest(config)
    protocol['c133']=protocol.pop('c132')
    protocol['c133'].update(
        wrapper_sha256=sha256(__file__),
        prior_c132_decision_sha256=sha256(
            REPO/'results/c132-diverse-active-session-20260929T1939Z/decision.json'),
        retry_reason='C132 turn04 reached frozen 512-token cap; shorten turns11-15, cap768, immediate natural-stop gate and preserved raw',
        max_tokens=768,total_timeout_s=6300)
    return protocol,config


def budget():
    path=REPO/'results/c132-diverse-active-session-20260929T1939Z/epoch-checkpoint.json'
    prior=strict_json(path.read_text())
    now=datetime.now(timezone.utc)
    wall=(datetime.fromisoformat('2026-09-29T13:31:15+00:00')+
          timedelta(hours=12)-now).total_seconds()
    physical=prior['physical_remaining_lower_bound_s']
    reserve=6300+60+600
    if min(wall,physical)<reserve:
        raise GateError('C133 retry and closure not admitted by epoch budget')
    return {'schema':'c133-budget-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(path),
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall,'reserved_s':reserve,
            'physical_cap_s':28800,'wall_cap_s':43200}


def configure():
    parent.ROOT_NAME=ROOT_NAME
    parent.RUN_ID=RUN_ID
    parent.WORKLOAD=WORKLOAD
    parent.make=make
    parent.budget=budget


if __name__=='__main__':
    configure()
    parent.main()
