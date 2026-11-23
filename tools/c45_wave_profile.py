#!/usr/bin/env python3
"""Profiler-only C15 run, using C43 control/plain outputs as fixed references."""

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import c18_cpu_telemetry as telemetry
import c34b_wave_profile as base
from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c45-wave-profile-20260928T0846Z')
RUN_ID = 'c45-c15-profile-cold513'
SPEC = (RUN_ID, base.DIAGNOSTIC, 'C15_PROFILE', 1)
TOKEN_SHA = 'bc41ccff712f8f8e1984f374051135e315e346641c060beba985ae983e162ee0'
C43 = Path('results/c43-wave-critical-20260928T0809Z')
C44_FAILURE = Path('results/c44-wave-profile-20260928T0833Z/decision.json')
ORIGINAL_FROZEN = base.frozen


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def references():
    control = strict_json((C43 / 'c43-control-cold513-receipt.json').read_text())
    plain = strict_json((C43 / 'c43-c15-plain-cold513-receipt.json').read_text())
    if control['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       plain['status'] != 'PASS_DIAGNOSTIC_BRIDGE' or \
       control['message_sha256'] != plain['message_sha256'] or \
       control['token_ids_sha256'] != TOKEN_SHA or plain['token_ids_sha256'] != TOKEN_SHA:
        raise GateError('C45 C43 reference receipts invalid')
    return control, plain


def overall(root):
    top = strict_json((root / 'protocol.json').read_text())
    control, plain = references()
    if top['schema'] != 'c45-wave-profile-protocol-v1' or \
       top['parent_c44_failure_sha256'] != sha256(C44_FAILURE) or \
       strict_json(C44_FAILURE.read_text())['status'] != 'FAIL_HARNESS_PROFILER_TRACE_ENV_NO_MODEL' or \
       top['profiler_trace_mode'] != 'nvtx' or \
       top['parent_c43_decision_sha256'] != sha256(C43 / 'decision.json') or \
       top['c43_control_receipt_sha256'] != sha256(C43 / 'c43-control-cold513-receipt.json') or \
       top['c43_plain_receipt_sha256'] != sha256(C43 / 'c43-c15-plain-cold513-receipt.json') or \
       top['runner_sha256'] != sha256(__file__) or \
       top['cpu_telemetry_sha256'] != sha256(telemetry.__file__) or \
       top['input_sha256'] != sha256(root / 'input.json') or \
       top['usage_contract_sha256'] != sha256(root / 'usage-contract.json') or \
       top['official_prompt_ids_sha256'] != TOKEN_SHA or \
       dt.datetime.now(ZoneInfo('Europe/Lisbon')).date().isoformat() != top['template_local_date'] or \
       control['message_sha256'] != top['reference_message_sha256']:
        raise GateError('C45 reference/source/date/input freeze differs')
    return top


def frozen(root, spec):
    protocol, config, tasks = ORIGINAL_FROZEN(root, spec)
    top = overall(root)
    protocol['campaign_id'] = 'tesy-c45-wave-profile-20260928'
    protocol['c45'] = {'runner_sha256': sha256(__file__),
                       'cpu_telemetry_sha256': sha256(telemetry.__file__),
                       'parent_c43_decision_sha256': sha256(C43 / 'decision.json'),
                       'parent_c44_failure_sha256': sha256(C44_FAILURE),
                       'profiler_trace_mode': top['profiler_trace_mode'],
                       'reference_message_sha256': top['reference_message_sha256'],
                       'profiled_timing_promotable': False}
    return protocol, config, tasks


def physical_budget(root):
    idle = sum(strict_json(path.read_text())['duration_s']
               for path in Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed() + idle + 2400 + 900 + 300 + 90 > 16*3600:
        raise GateError('C45 physical budget cannot cover profile and cleanup')


def install_hooks():
    base.ROOT = ROOT
    base.SPECS = (SPEC,)
    base.BY_ID = {RUN_ID: SPEC}
    base.TOKEN_SHA = TOKEN_SHA
    base.overall = overall
    base.frozen = frozen
    base.physical_budget = physical_budget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--measurement-commit')
    args = parser.parse_args()
    if args.root != ROOT or not (ROOT / 'raw').is_dir() or not (ROOT / 'protocols').is_dir():
        raise GateError('C45 root differs')
    install_hooks()
    if args.freeze:
        protocol, _, _ = frozen(ROOT, SPEC)
        save_new(ROOT / 'protocols' / f'{RUN_ID}.json', protocol)
        print(json.dumps({'status': 'FROZEN', 'protocol_sha256': sha256(ROOT / 'protocols' / f'{RUN_ID}.json')}))
        return 0
    if not args.measurement_commit:
        parser.error('--measurement-commit required')
    rc = base.run_arm(ROOT, SPEC, args.measurement_commit)
    if rc:
        return rc
    receipt = strict_json((ROOT / f'{RUN_ID}-receipt.json').read_text())
    control, plain = references()
    match = receipt['message_sha256'] == control['message_sha256'] == plain['message_sha256'] and \
            receipt['token_ids_sha256'] == control['token_ids_sha256']
    comparison = {'schema': 'c45-profile-output-comparison-v1',
                  'status': 'PASS_GREEDY_FOUR_TOKEN_BRIDGE' if match else 'FAIL_SAME_PROFILE_FIDELITY',
                  'profile_receipt_sha256': sha256(ROOT / f'{RUN_ID}-receipt.json'),
                  'reference_control_sha256': sha256(C43 / 'c43-control-cold513-receipt.json'),
                  'reference_plain_sha256': sha256(C43 / 'c43-c15-plain-cold513-receipt.json'),
                  'message_sha256': receipt['message_sha256'],
                  'reference_message_sha256': control['message_sha256'],
                  'limit': 'four greedy output tokens only; full logits bitwise NOT_RUN'}
    save_new(ROOT / 'output-comparison.json', comparison)
    print(json.dumps({'status': comparison['status']}))
    return 0 if match else 1


if __name__ == '__main__':
    raise SystemExit(main())
