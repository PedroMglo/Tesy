#!/usr/bin/env python3
"""Independent uniform44 paired gate, preserving full output and input work."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from statistics import median
import c128_slots40_analyze as previous
import c141_slots44_server as family
from c2_gate import GateError,strict_json
from run_bounded import sha256


def paired_gate(pairs,n):
    if len(pairs)!=n or any(set(p['gain_percent'])!=set(previous.METRICS) for p in pairs):
        raise GateError('incomplete uniform44 pairs')
    med={m:median(p['gain_percent'][m] for p in pairs) for m in previous.METRICS}
    if not all(p['same_work'] for p in pairs):return 'INCONCLUSIVE_OUTPUT_DIVERGENCE',med
    go=med['warm_decode_s']>=8 and all(p['gain_percent']['warm_decode_s']>0 for p in pairs) and all(med[k]>=-5 for k in previous.PROTECTED)
    return (('SCREEN_GO_UNIFORM44_NOMINAL153' if n==2 else 'CONFIRMED_UNIFORM44_NOMINAL153') if go else
        ('NO_GO_UNIFORM44_NOMINAL153' if n==2 else 'NO_GO_CONFIRM_UNIFORM44_NOMINAL153')),med


def analyze(root):
    family.configure(root);pre=strict_json((root/'preflight.json').read_text());policy=strict_json((root/'resource-policy.json').read_text())
    frozen=strict_json((root/'confirm-policy.json').read_text());n=len(family.campaign.ORDER)//2
    if frozen!=family.screen_policy(root) or sha256(root/'confirm-policy.json')!=pre['confirm_policy_sha256']:
        raise GateError('uniform44 policy changed')
    first=strict_json((root/'raw'/f'{family.campaign.ORDER[0][0]}.receipt.json').read_text());commit=first['measurement_commit']
    if len(commit)!=40:raise GateError('full measurement SHA required')
    runs=[previous.arm(root,spec,commit,policy,slots_by_role={'control':'40s','candidate':'44s'}) for spec in family.campaign.ORDER]
    pairs=[]
    for number in range(1,n+1):
        a=next(r for r in runs if r['role']=='control' and r['pair']==number)
        b=next(r for r in runs if r['role']=='candidate' and r['pair']==number)
        equal=all(a[k]==b[k] for k in ('completion_tokens','prompt_tokens','cached_tokens','evaluated_tokens','tokenization_sha256','messages'))
        for r in (a,b):
            if r['prompt_tokens']!=[2043,2197] or (r['cached_tokens'],r['evaluated_tokens'])!=(2044,153):
                raise GateError('uniform44 official nominal153 accounting differs')
            raw=strict_json((root/'raw'/f'{r["run_id"]}.json').read_text())
            if any(x['timings']['predicted_n']!=x['usage']['completion_tokens'] for x in raw['results']):
                raise GateError('decode output/token accounting differs')
        gains={k:100*(a['metrics'][k]-b['metrics'][k])/a['metrics'][k] for k in previous.METRICS}
        pairs.append({'pair':number,'control':a['run_id'],'candidate':b['run_id'],'same_work':equal,'gain_percent':gains,
            'start_delta_candidate_minus_control_c':[y-x for x,y in zip(a['start_temperature_c'],b['start_temperature_c'])]})
    status,med=paired_gate(pairs,n)
    for r in runs:r.pop('messages')
    timing={'runs':runs,'pairs':pairs,'median_paired_gain_percent':med,'measurement_commit':commit}
    decision={'schema':f'{family.UNIT}-decision-v1','status':status,'evidence':'MEDIDO_NO_TARGET',
        'measurement_commit':commit,'primary':'warm_decode_s','protected':list(previous.PROTECTED),
        'median_paired_gain_percent':med,'pairs':pairs,'numerical_decision_sha256':sha256(family.NUMERIC/'decision.json'),
        'M3':'slots40 partial;44 session/quality NOT_RUN','M4':'NOT_DEMONSTRATED','default_changed':False,'publication':'LOCAL_ONLY'}
    manifest={'schema':f'{family.UNIT}-manifest-v1','measurement_commit':commit,
        'raw':{f.name:{'bytes':f.stat().st_size,'sha256':sha256(f)} for f in sorted((root/'raw').iterdir()) if f.is_file()}}
    elapsed=sum((datetime.fromisoformat(strict_json((root/'raw'/f'{s[0]}.receipt.json').read_text())['ended_utc'])-
                 datetime.fromisoformat(strict_json((root/'raw'/f'{s[0]}.receipt.json').read_text())['started_utc'])).total_seconds() for s in family.campaign.ORDER)
    old=strict_json(family.CHECKPOINT.read_text());charged=old['physical_charged_upper_estimate_s']+elapsed
    checkpoint={'epoch_id':'post-c119-20260929T133115Z','utc':datetime.now(timezone.utc).isoformat(),
        'physical_charged_upper_estimate_s':charged,'physical_remaining_lower_bound_s':28800-charged,
        'wall_remaining_s':(family.DEADLINE-datetime.now(timezone.utc)).total_seconds(),
        'family_live_elapsed_s':elapsed,'includes':'per-arm60s inventory, server, launch/preflight/cleanup; counted once',
        'prior_checkpoint_sha256':sha256(family.CHECKPOINT)}
    return timing,decision,manifest,checkpoint

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);a=ap.parse_args();root=a.root.resolve()
    for name,row in zip(('timing-pairs.json','decision.json','manifest.json','epoch-checkpoint.json'),analyze(root)):
        family.campaign.save_new(root/name,row)
    print(json.dumps({'status':strict_json((root/'decision.json').read_text())['status']}))
