"""Selected native head boundary, not an integrated speculation speed claim."""
import argparse
import json
import math
from pathlib import Path
import numpy as np


def validate(value,fixture):
    if value.get('status')!='PASS_SELECTED_HEAD_BOUNDARY' or value.get('B')!=8 or value.get('K')!=7 or value.get('head_ngl')!=1:
        raise ValueError('head profile/status changed')
    if value.get('head_target_layers')!=[2,18,33] or value.get('official_prefix_ids')!=fixture['ids']:
        raise ValueError('feature indices or official input IDs changed')
    if value.get('target_profile')!='C75/P12/slots40/ub32/ctx8192/GOMPunset':raise ValueError('wrong target profile')
    ids=value.get('native_proposed_ids');winners=value.get('target_native_argmax')
    for seq,count in ((ids,7),(winners,8)):
        if type(seq) is not list or len(seq)!=count or any(type(x) is not int or not 0<=x<201088 for x in seq):raise ValueError('missing/invalid native proposal/logit IDs')
    accepted=0
    while accepted<7 and ids[accepted]==winners[accepted]:accepted+=1
    if type(value.get('accepted_draft_count')) is not int or value['accepted_draft_count']!=accepted or value.get('new_confirmable_tokens')!=accepted+1 or value.get('correction_or_bonus')!=winners[accepted]:raise ValueError('anchor/acceptance/correction accounting wrong')
    for key in ('draft_seven_s','verification_head_processing_s','prefill_head_processing_s','prefill_total_s','verify_plus_head_process_s'):
        x=value.get(key)
        if type(x) not in (int,float) or not math.isfinite(x) or x<=0:raise ValueError('missing/nonfinite duration')
    if value['prefill_total_s']<value['prefill_head_processing_s'] or value['verify_plus_head_process_s']<value['verification_head_processing_s']:raise ValueError('overlapping phase accounting invalid')
    checks=value.get('R1_causal_checks');anchor=value.get('anchor_known_input')
    if type(anchor) is not int or not 0<=anchor<201088 or type(checks) is not list or len(checks)!=8:raise ValueError('causal coverage missing')
    for known,row in enumerate(checks,1):
        if row!={'known':known,'prefix_only_inputs':([anchor]+ids)[:known]+[0]*(8-known),'preceding_rows_bitwise':True}:raise ValueError('causal prefix-only proof wrong/missing')
    return {'status':'PASS_SELECTED_HEAD_FEATURE_BOUNDARY','accepted_draft_count':accepted,'L':accepted+1,
            'observed_draft_plus_feature_processing_s':value['draft_seven_s']+value['verification_head_processing_s'],
            'scope':'One selected grid, no integrated throughput/continuity/product qualification'}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('fixture',type=Path);p.add_argument('case');p.add_argument('neutral_reference',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=json.loads((a.directory/'result.json').read_text());fixture=json.loads(a.fixture.read_text())[a.case];result=validate(value,fixture)
    observed=a.directory/'feature-enabled-historical.logits.f32'
    reference=a.neutral_reference
    if observed.stat().st_size!=8*201088*4 or reference.stat().st_size!=observed.stat().st_size or observed.read_bytes()!=reference.read_bytes():raise ValueError('feature extraction changes qualified same-B target output')
    for name in ('feature-enabled-historical.logits.f32','head-verification.logits.f32'):
        vals=np.fromfile(a.directory/name,dtype='<f4')
        if vals.size!=8*201088 or not np.isfinite(vals).all():raise ValueError('head target complete finite rows missing')
    result['feature_enabled_same_B_target_logits_bitwise']=True
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'])

if __name__=='__main__':main()
