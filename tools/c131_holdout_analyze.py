#!/usr/bin/env python3
"""Revalidate and summarize the prospectively frozen C131 holdout."""

from datetime import datetime, timezone
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c131_holdout_server as campaign


ROOT = campaign.REPO / 'results' / campaign.ROOT_NAME


def analyze():
    arms = []
    for spec in campaign.ORDER:
        run_id, profile = spec
        receipt_path = ROOT / 'raw' / f'{run_id}.receipt.json'
        raw_path = ROOT / 'raw' / f'{run_id}.json'
        inventory_path = ROOT / 'raw' / f'{run_id}.start-inventory.receipt.json'
        receipt = strict_json(receipt_path.read_text())
        raw = strict_json(raw_path.read_text())
        protocol, config = campaign.frozen(ROOT, spec)
        if receipt['status'] != 'PASS_HOLDOUT_ARM_EVALUATED' or \
           receipt['run_id'] != run_id or receipt['arm'] != profile or \
           receipt['model_launch_observed'] is not True or \
           receipt['measurement_commit'] != '3a695ca412b4198e3405b2054fb450bb7193350f' or \
           receipt['raw_sha256'] != sha256(raw_path) or \
           receipt['inventory_receipt_sha256'] != sha256(inventory_path):
            raise GateError(f'C131 receipt or raw identity invalid: {run_id}')
        maxima, results = campaign.validate(ROOT, spec, protocol, config, raw)
        if maxima != receipt['maxima'] or results != receipt['results']:
            raise GateError(f'C131 independent revalidation differs: {run_id}')
        arms.append({'run_id': run_id, 'profile': profile,
                     'receipt_sha256': sha256(receipt_path),
                     'raw_sha256': sha256(raw_path),
                     'inventory_sha256': sha256(inventory_path),
                     'tokenization_sha256': sha256(ROOT/'raw'/f'{run_id}.tokenization.json'),
                     'launch_sha256': sha256(ROOT/'raw'/f'{run_id}.launch.json'),
                     'pass_count': sum(row['status'] == 'PASS' for row in results),
                     'maxima': maxima,
                     'results': results,
                     'started_utc': receipt['started_utc'],
                     'ended_utc': receipt['ended_utc']})
    control, candidate = arms
    ids_equal = strict_json((ROOT/'raw'/f'{control["run_id"]}.tokenization.json').read_text()) == \
        strict_json((ROOT/'raw'/f'{candidate["run_id"]}.tokenization.json').read_text())
    messages_equal = [a['message_sha256'] == b['message_sha256']
                      for a, b in zip(control['results'], candidate['results'])]
    no_loss = all(a['status'] != 'PASS' or b['status'] == 'PASS'
                  for a, b in zip(control['results'], candidate['results']))
    all_pass = candidate['pass_count'] == 8 and control['pass_count'] == 8
    status = ('PASS_HOLDOUT_8_OF_8_NO_QUALITY_LOSS' if
              no_loss and all_pass and ids_equal and all(messages_equal) else
              'FAIL_HOLDOUT_QUALITY_OR_IDENTITY')
    return {'schema': 'c131-holdout-analysis-v1',
            'utc': datetime.now(timezone.utc).isoformat(),
            'status': status,
            'evidence_class': 'MEDIDO_NO_TARGET',
            'measurement_commit': '3a695ca412b4198e3405b2054fb450bb7193350f',
            'quality_policy_sha256': sha256(ROOT/'quality-policy.json'),
            'workload_sha256': sha256(campaign.holdout.TASKS),
            'prompt_token_arrays_equal': ids_equal,
            'full_assistant_messages_equal_by_task': dict(zip(
                [row['id'] for row in control['results']], messages_equal)),
            'no_control_task_lost': no_loss,
            'arms': arms,
            'claim_limit': 'Eight new frozen tasks on one machine/profile pair; no general quality equivalence or causal timing claim.'}


def main():
    result = analyze()
    campaign.save_new(ROOT/'analysis.json', result)
    print(json.dumps({'status': result['status'],
                      'pass_counts': [x['pass_count'] for x in result['arms']],
                      'messages_equal': all(result['full_assistant_messages_equal_by_task'].values())}))


if __name__ == '__main__':
    main()
