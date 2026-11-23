#!/usr/bin/env python3
"""Revalidate C133 without relaxing the frozen twenty-turn quality gate."""

from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c133_diverse_session_retry as retry


ROOT=retry.REPO/'results'/retry.ROOT_NAME


def analyze():
    retry.configure()
    run_id=retry.RUN_ID
    raw_path=ROOT/'raw'/f'{run_id}.json'
    receipt_path=ROOT/'raw'/f'{run_id}.receipt.json'
    receipt=strict_json(receipt_path.read_text())
    raw=strict_json(raw_path.read_text())
    protocol,config=retry.parent.frozen(ROOT)
    if receipt['measurement_commit']!='ff9d1d7ff6d7df99156cc8e33a613b99afbc4ed4' or \
       receipt['raw_sha256']!=sha256(raw_path) or \
       receipt['model_launch_observed'] is not True or \
       receipt['inventory_receipt_sha256']!=sha256(ROOT/'raw'/f'{run_id}.start-inventory.receipt.json'):
        raise GateError('C133 receipt/raw/freeze provenance invalid')
    maxima,details,timing=retry.parent.validate(ROOT,protocol,config,raw)
    if maxima!=receipt['maxima'] or details!=receipt['results'] or timing!=receipt['timing']:
        raise GateError('C133 revalidation differs from original receipt')
    failures=[{'id':row['id'],'missing':row['grade']['missing']}
              for row in details if row['grade']['status']!='PASS']
    status=('PASS_DIVERSE_ACTIVE_SESSION' if
            timing['duration_pass'] and not failures else
            'SESSION_QUALITY_OR_DURATION_NO_GO')
    if status!=receipt['status']:
        raise GateError('C133 effective status differs from frozen gate')
    prompts=[row['prompt_tokens'] for row in details]
    finals=[row['first_final_content_s'] for row in details]
    return {'schema':'c133-analysis-v1','utc':datetime.now(timezone.utc).isoformat(),
            'status':status,'evidence_class':'MEDIDO_NO_TARGET',
            'measurement_commit':receipt['measurement_commit'],
            'receipt_sha256':sha256(receipt_path),'raw_sha256':sha256(raw_path),
            'inventory_sha256':receipt['inventory_receipt_sha256'],
            'official_tokenization_sha256':sha256(ROOT/'raw'/f'{run_id}.tokenization.json'),
            'completed_requests':len(details),'natural_finishes':sum(
                row['finish_reason']=='stop' for row in raw['results']),
            'content_pass_count':len(details)-len(failures),'content_failures':failures,
            'active_block_s':timing['active_block_s'],
            'session_span_s':timing['session_span_s'],
            'request_active_sum_s':timing['request_active_sum_s'],
            'request_duty_fraction':timing['request_active_sum_s']/timing['session_span_s'],
            'spaced_gaps_s':timing['adjacent_gaps_s'][14:],
            'max_official_prompt_tokens':max(prompts),
            'min_official_prompt_tokens':min(prompts),
            'median_first_final_content_s':median(finals),
            'maxima':maxima,
            'limits':['Turn02 omitted literal project name Aster; frozen validator fails',
                      'Finite 20-task synthetic conversation, not general quality proof',
                      'No restart/KV persistence test and no M4 latency qualification']}


def main():
    value=analyze()
    with (ROOT/'analysis.json').open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')
    print(json.dumps({'status':value['status'],
                      'requests':value['completed_requests'],
                      'content_pass':value['content_pass_count'],
                      'active_block_s':value['active_block_s'],
                      'session_span_s':value['session_span_s']}))


if __name__=='__main__':
    main()
