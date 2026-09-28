#!/usr/bin/env python3
"""Fresh identity for the C41 prelaunch commit-argument failure."""

from pathlib import Path

import c41_boundary as base
from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path('results/c41b-8k-boundary-20260928T0723Z')
RUN_ID = 'c41b-p12-boundary7936'
PARENT_FAILURE = Path('results/c41-8k-boundary-20260928T0715Z/decision.json')
ORIGINAL_SPECS = base.specs


def specs(root):
    top = strict_json((root / 'protocol.json').read_text())
    if top['launcher_sha256'] != sha256(__file__) or \
       top['parent_c41_failure_sha256'] != sha256(PARENT_FAILURE) or \
       strict_json(PARENT_FAILURE.read_text())['status'] != 'FAIL_HARNESS_COMMIT_ARGUMENT_NO_MODEL':
        raise GateError('C41b launcher or parent identity changed')
    protocol, config, tasks, model = ORIGINAL_SPECS(root)
    protocol['c41']['launcher_sha256'] = sha256(__file__)
    protocol['c41']['parent_c41_failure_sha256'] = sha256(PARENT_FAILURE)
    return protocol, config, tasks, model


def main():
    base.ROOT = ROOT
    base.RUN_ID = RUN_ID
    base.specs = specs
    return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
