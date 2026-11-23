#!/usr/bin/env python3
"""Fresh 8K boundary identity with bounded high-frequency monitor reread."""

from pathlib import Path

import c18_cpu_telemetry as telemetry
import c41_boundary as base
from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path('results/c42-8k-boundary-20260928T0741Z')
RUN_ID = 'c42-p12-boundary7936'
PARENT_FAILURE = Path('results/c41b-8k-boundary-20260928T0723Z/decision.json')
ORIGINAL_SPECS = base.specs


def specs(root):
    top = strict_json((root / 'protocol.json').read_text())
    if top['launcher_sha256'] != sha256(__file__) or \
       top['parent_c41b_failure_sha256'] != sha256(PARENT_FAILURE) or \
       top['cpu_telemetry_sha256'] != sha256(telemetry.__file__) or \
       strict_json(PARENT_FAILURE.read_text())['status'] != 'FAIL_RESOURCES_OR_EVIDENCE':
        raise GateError('C42 launcher, telemetry or parent identity changed')
    protocol, config, tasks, model = ORIGINAL_SPECS(root)
    protocol['c41']['launcher_sha256'] = sha256(__file__)
    protocol['c41']['parent_c41b_failure_sha256'] = sha256(PARENT_FAILURE)
    protocol['c41']['cpu_telemetry_sha256'] = sha256(telemetry.__file__)
    return protocol, config, tasks, model


def main():
    base.ROOT = ROOT
    base.RUN_ID = RUN_ID
    base.specs = specs
    return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
