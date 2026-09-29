#!/usr/bin/env python3
"""Recheck C130b quality, historical prompts/messages and physical ledger."""

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from c118_start_inventory import require_inventory
from run_bounded import sha256
import c130b_slots40_quality as campaign


REPO = Path(__file__).resolve().parents[1]


def save_new(path, value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def analyze(root):
    campaign.configure()
    p,c = campaign.prior.campaign.frozen(root)
    run_id = campaign.RUN_ID
    rawdir = root/'raw'
    rawpath = rawdir/(run_id+'.json')
    rpath = rawdir/(run_id+'.receipt.json')
    ipath = rawdir/(run_id+'.start-inventory.receipt.json')
    raw,receipt,inventory = [strict_json(path.read_text()) for path in (rawpath,rpath,ipath)]
    launch = strict_json((rawdir/(run_id+'.launch.json')).read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    power = {key:policy['power'][key] for key in ('source','profile')}
    at = datetime.fromisoformat(launch['start_inventory']['popen_invoked_utc'])
    require_inventory(root,run_id,inventory,policy=policy,
                      cap_bytes=campaign.prior.CAP,expected_power=power,
                      duration_s=60,now=at,max_age_s=3)
    if receipt['status'] != 'PASS_QUALITY_12_OF_12' or \
       receipt['model_launch_observed'] is not True or \
       receipt['raw_sha256'] != sha256(rawpath) or \
       receipt['inventory_receipt_sha256'] != sha256(ipath) or \
       launch['start_inventory']['receipt_sha256'] != sha256(ipath) or \
       receipt['stop_reasons'] != [] or len(receipt['results']) != 12 or \
       any(x['status'] != 'PASS' for x in receipt['results']):
        raise GateError('C130b receipt/launch/quality incomplete')
    maxima, validations = campaign.prior.campaign.validate(root,p,c,raw)
    if maxima != receipt['maxima'] or validations != receipt['results']:
        raise GateError('C130b independent revalidation differs')
    prior = [strict_json((REPO/path).read_text()) for path in (
        'results/c40-quality-recovery-20260928T0528Z/raw/c40-p12.json',
        'results/c126-wave-quality-20260929T1610Z/raw/c126-c75-quality12.json')]
    tokenization = strict_json((rawdir/(run_id+'.tokenization.json')).read_text())
    historical_tokens = [strict_json((REPO/path).read_text()) for path in (
        'results/c40-quality-recovery-20260928T0528Z/raw/c40-p12.tokenization.json',
        'results/c126-wave-quality-20260929T1610Z/raw/c126-c75-quality12.tokenization.json')]
    same_tokens = all(tokenization == x for x in historical_tokens)
    same_messages = all(
        [x['message'] for x in raw['results']] == [x['message'] for x in old['results']]
        for old in prior)
    if not same_tokens:
        raise GateError('C130b official prompt arrays differ from frozen control')
    prior_checkpoint_path = REPO/'results/c129-slots40-confirm-20260929T1735Z/epoch-checkpoint.json'
    prior_checkpoint = strict_json(prior_checkpoint_path.read_text())
    envelope = (datetime.fromisoformat(receipt['ended_utc'])-
                datetime.fromisoformat(receipt['started_utc'])).total_seconds()
    charged = prior_checkpoint['physical_charged_upper_estimate_s']+120+envelope
    now = datetime.now(timezone.utc)
    epoch_start = datetime.fromisoformat('2026-09-29T13:31:15+00:00')
    checkpoint = {'schema':'c130b-epoch-checkpoint-v1','utc':now.isoformat(),
                  'prior_checkpoint_sha256':sha256(prior_checkpoint_path),
                  'c130_failed_live_upper_s':120,'c130b_live_envelope_s':envelope,
                  'c130b_server_elapsed_s':raw['elapsed_s'],
                  'physical_charged_upper_estimate_s':charged,
                  'physical_remaining_lower_bound_s':28800-charged,
                  'wall_remaining_s':(epoch_start+timedelta(hours=12)-now).total_seconds(),
                  'raw_c130b_bytes':sum(x.stat().st_size for x in rawdir.iterdir() if x.is_file()),
                  'raw_limit_bytes':20*2**30}
    decision = {'schema':'c130b-quality-decision-v1','status':'PASS_QUALITY_12_OF_12',
                'measurement_commit':receipt['measurement_commit'],
                'pass_count':12,'finish_reason_stop_count':sum(x['finish_reason']=='stop' for x in raw['results']),
                'official_prompt_arrays_equal_c40_and_c126':same_tokens,
                'all_messages_equal_c40_and_c126':same_messages,
                'first_final_median_s':median(x['stream_metrics']['first_final_content_chunk_s']
                                               for x in raw['results']),
                'raw_sha256':sha256(rawpath),'receipt_sha256':sha256(rpath),
                'maxima':maxima,'M4':'NOT_DEMONSTRATED',
                'limitations':['12 frozen synthetic tasks only; holdout8 and diverse conversation NOT_RUN',
                               'C40 timing across days descriptive only',
                               'full independent 8K attention/KV NOT_RUN'],
                'default_changed':False,'publication':'LOCAL_ONLY'}
    manifest = {'schema':'c130b-manifest-v1','raw':{
        x.name:{'bytes':x.stat().st_size,'sha256':sha256(x)}
        for x in sorted(rawdir.iterdir()) if x.is_file()}}
    return decision,checkpoint,manifest


def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path)
    root=ap.parse_args().root.resolve()
    for name,row in zip(('decision.json','epoch-checkpoint.json','manifest.json'),analyze(root)):
        save_new(root/name,row)
    print(json.dumps({'status':'PASS_QUALITY_12_OF_12'}))


if __name__=='__main__':
    main()
