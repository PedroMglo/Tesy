#!/usr/bin/env python3
"""C134b: same frozen 8K boundary via a detached user service."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import c134_slots40_boundary as parent
from c2_gate import GateError, strict_json
from run_bounded import sha256


REPO=Path(__file__).resolve().parents[1]
ROOT_NAME='c134b-slots40-boundary-20260929T2140Z'
RUN_ID='c134b-c75-slots40-boundary7936'
_make=parent.make


def make(root):
    protocol,config=_make(root)
    protocol['schema_version']='c134b-protocol-v1'
    protocol['c134b']=protocol.pop('c134')
    protocol['c134b'].update(
        wrapper_sha256=sha256(__file__),
        prior_c134_interruption_sha256=sha256(
            REPO/'results/c134-slots40-boundary-20260929T2131Z/interruption.json'),
        launcher='detached unique systemd user service, E18/zero-swap',
        model_free_scope_smoke_sha256=sha256(
            root/'detached-scope-smoke.json'))
    return protocol,config


def budget():
    path=REPO/'results/c134-slots40-boundary-20260929T2131Z/epoch-checkpoint.json'
    prior=strict_json(path.read_text())
    now=datetime.now(timezone.utc)
    wall=(datetime.fromisoformat('2026-09-29T13:31:15+00:00')+
          timedelta(hours=12)-now).total_seconds()
    physical=prior['physical_remaining_lower_bound_s']
    reserve=2400+60+600+1800
    if min(wall,physical)<reserve:
        raise GateError('C134b and remaining discriminant/closure not admitted')
    return {'schema':'c134b-budget-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(path),
            'physical_remaining_lower_bound_s':physical,
            'wall_remaining_s':wall,'reserved_s':reserve,
            'detached_service_unit':'tesy-c134b-boundary.service'}


def configure():
    parent.ROOT_NAME=ROOT_NAME
    parent.RUN_ID=RUN_ID
    parent.make=make
    parent.budget=budget


if __name__=='__main__':
    configure()
    parent.main()
