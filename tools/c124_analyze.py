#!/usr/bin/env python3
"""Analyze three C124 pairs through the C120 strong inventory gate."""

import argparse
from datetime import datetime
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256
from c118_start_inventory import require_inventory
import c117_analyze as previous
import c124_nominal_confirm as confirm
from c120_nominal_server import CAP, save_new


def confirmation_gate(pairs):
    if len(pairs) != 3:
        raise GateError('C124 requires three fresh pairs')
    medians={k:median(p['gain_percent'][k] for p in pairs) for k in previous.METRICS}
    primary='warm_first_final_s'
    protected=('warm_decode_s','cold_decode_s','cold_first_final_s','cold_prefill_s')
    go=medians[primary]>=8 and all(p['gain_percent'][primary]>0 for p in pairs) and all(medians[k]>=-5 for k in protected)
    return go,medians,primary,protected


def analyze(root):
    order = confirm.campaign.ORDER
    frozen = strict_json((root/'preflight.json').read_text())
    policy = strict_json((root/'confirm-policy.json').read_text())
    resource = strict_json((root/'resource-policy.json').read_text())
    if policy != confirm.confirm_policy(root) or sha256(root/'confirm-policy.json') != frozen['confirm_policy_sha256']:
        raise GateError('C124 policy changed')
    power = {k:resource['power'][k] for k in ('source','profile')}
    rows=[]; commit=None
    for run_id,arm,pair in order:
        receipt_path=root/'raw'/f'{run_id}.receipt.json'
        receipt=strict_json(receipt_path.read_text())
        inv_path=root/'raw'/f'{run_id}.start-inventory.receipt.json'
        inv=strict_json(inv_path.read_text())
        launch=strict_json((root/'raw'/f'{run_id}.launch.json').read_text())
        if commit is None: commit=receipt['measurement_commit']
        if receipt.get('status')!='PASS_SCREEN_ARM_TESTED_SCOPE' or receipt.get('run_id')!=run_id or \
           receipt.get('measurement_commit')!=commit or receipt.get('model_launch_observed') is not True or \
           receipt.get('start_inventory_receipt_sha256')!=sha256(inv_path) or \
           launch.get('run_id')!=run_id or launch.get('start_inventory',{}).get('receipt_sha256')!=sha256(inv_path):
            raise GateError('C124 receipt/launch/inventory chain invalid: '+run_id)
        launch_at=datetime.fromisoformat(launch['start_inventory']['popen_invoked_utc'])
        require_inventory(root,run_id,inv,policy=resource,cap_bytes=CAP,
                          expected_power=power,duration_s=60,now=launch_at,max_age_s=3)
        rows.append(previous.run_row(root,pair,arm,commit,resource,run_prefix='c124'))
    pairs=[]
    for n in (1,2,3):
        control=next(x for x in rows if x['pair']==n and x['arm']=='control')
        candidate=next(x for x in rows if x['pair']==n and x['arm']=='candidate')
        gains={k:100*(control['metrics'][k]-candidate['metrics'][k])/control['metrics'][k] for k in previous.METRICS}
        pairs.append({'pair':n,'control':control['run_id'],'candidate':candidate['run_id'],
                      'gain_percent':gains,
                      'start_delta_candidate_minus_control_c':[b-a for a,b in zip(control['start_cpu_gpu_nvme_c'],candidate['start_cpu_gpu_nvme_c'])]})
    go,medians,primary,protected=confirmation_gate(pairs)
    timing={'schema':'c124-timing-v1','measurement_commit':commit,'runs':rows,'pairs':pairs,
            'median_paired_gain_percent':medians,'start_regime':'OPERATIONAL_WARM_NO_NARROW_THERMAL_MATCH'}
    decision={'schema':'c124-decision-v1','status':'CONFIRMED_OPERATIONAL_NOMINAL153' if go else 'NO_GO_CONFIRM_OPERATIONAL_NOMINAL153',
              'measurement_commit':commit,'primary':primary,'protected':list(protected),'pairs':pairs,
              'median_paired_gain_percent':medians,'C121':'SCREEN_GO_OPERATIONAL_NOMINAL153',
              'C100':'NO_GO_CONFIRM_PRESERVED','C117':'FAIL_RESOURCES_OR_EVIDENCE_PRESERVED',
              'M3':'C52B_TESTED_SCOPE_UNCHANGED','M4':'NOT_DEMONSTRATED',
              'publication':'LOCAL_ONLY','default_changed':False}
    manifest={'schema':'c124-manifest-v1','measurement_commit':commit,
              'raw':{p.name:{'bytes':p.stat().st_size,'sha256':sha256(p)} for p in sorted((root/'raw').iterdir()) if p.is_file()}}
    return timing,decision,manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    root=args.root.resolve()
    timing,decision,manifest=analyze(root)
    for name,row in [('timing-pairs.json',timing),('decision.json',decision),('manifest.json',manifest)]:
        save_new(root/name,row)
    print(decision['status'])


if __name__=='__main__':
    main()
