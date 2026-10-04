"""Strict finite native greedy grid loop accounting and independent raw comparison."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from block_head_grid_contract import accept_grid


def validate(value,fixture):
    if value.get('status')!='MEASURED_NATIVE_CONFIRMED_LOOP' or value.get('official_prefix_ids')!=fixture['ids'] or value.get('mode') not in ('ar','head-diagnostic','head-measure'):
        raise ValueError('native loop/input/profile status invalid')
    cap=value.get('count_limit');tokens=value.get('native_confirmed_ids');steps=value.get('iterations');mode=value['mode']
    if cap not in (16,32) or type(tokens) is not list or len(tokens)<2 or type(steps) is not list or not steps or any(type(t) is not int or not 0<=t<201088 for t in tokens):raise ValueError('missing native confirmed outputs/iterations')
    if value.get('initial_anchor')!=tokens[0] or value.get('decode_confirmed_excluding_anchor')!=len(tokens)-1 or len(tokens)>cap+1:raise ValueError('anchor/token counts wrong')
    if value.get('finish') not in ('EOS','DIAGNOSTIC_CAP') or (value['finish']=='DIAGNOSTIC_CAP' and len(tokens)!=cap+1):raise ValueError('incomplete cap/finish')
    for key in ('wall_s','prefill_total_s'):
        x=value.get(key)
        if type(x) not in (int,float) or not math.isfinite(x) or x<=0:raise ValueError('missing/invalid native wall')
    for key in ('prefill_head_processing_s','draft_total_s','verification_head_processing_s','diagnostic_reference_s'):
        x=value.get(key)
        if type(x) not in (int,float) or not math.isfinite(x) or x<0:raise ValueError('invalid phase span')
    if value['wall_s']<sum(value[k] for k in ('draft_total_s','verification_head_processing_s','diagnostic_reference_s')):raise ValueError('exclusive phase spans exceed containing wall')
    confirmed=[tokens[0]];origin=len(fixture['ids'])
    for index,row in enumerate(steps):
        if mode=='ar':
            if row.get('B')!=1 or row.get('input')!=confirmed[-1] or type(row.get('confirmed')) is not int:raise ValueError('AR trajectory/count invalid')
            confirmed.append(row['confirmed']);continue
        known=(len(confirmed)-1)%8+1;start=origin+((len(confirmed)-1)//8)*8
        inputs=row.get('target_inputs');winners=row.get('target_argmax');props=row.get('native_proposals')
        if row.get('B')!=8 or row.get('known_rows')!=known or row.get('grid_start')!=start or type(inputs) is not list or len(inputs)!=8 or inputs[:known]!=confirmed[-known:] or type(winners) is not list or len(winners)!=8 or type(props) is not list or len(props)!=(7 if known<8 else 0):raise ValueError('grid/position/input/proposal mapping invalid')
        if any(type(t) is not int or not 0<=t<201088 for t in (*inputs,*winners,*props)):raise ValueError('invalid native IDs')
        if mode=='head-measure' and (row.get('diagnostic_pattern')!='REAL_HEAD_UNMODIFIED' or inputs[known:]!=props[:8-known] or row.get('clean_R1_checked_rows')!=0):raise ValueError('measured head inputs overridden or diagnostic inside production timing')
        # Native EOS membership is checked independently by C++ vocabulary. Infer
        # the last observed EOS only at the terminal result, not from token count.
        eos=(tokens[-1],) if value['finish']=='EOS' and index==len(steps)-1 else ()
        expected=accept_grid(known,inputs,winners,remaining_output=cap-len(confirmed)+1,eos_ids=eos)
        for key in ('accepted_draft_count','feature_row'):
            if row.get(key)!=expected[key]:raise ValueError('native acceptance/feature-row accounting wrong')
        if row.get('new_confirmed')!=expected['new_ids']:raise ValueError('unverified token committed or output omitted')
        if mode=='head-diagnostic' and row.get('clean_R1_checked_rows')!=row['feature_row']-known+2:raise ValueError('clean reference coverage missing')
        confirmed+=expected['new_ids']
    if confirmed!=tokens or value.get('target_verification_calls')!=len(steps) or value.get('target_full_logit_rows')!=len(steps)*(1 if mode=='ar' else 8):raise ValueError('complete native loop cardinality/count mismatch')
    return {'status':'PASS_SELECTED_NATIVE_GRID_LOOP','mode':mode,'decode_confirmed_excluding_anchor':len(tokens)-1,'wall_s':value['wall_s'],'iterations':len(steps),'scope':'Selected native loop only, no general quality or utility claim'}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('fixture',type=Path);p.add_argument('case');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=json.loads((a.directory/'result.json').read_text());r=validate(value,json.loads(a.fixture.read_text())[a.case])
    if value['mode']=='head-diagnostic':
        patterns=[row['diagnostic_pattern'] for row in value['iterations']]
        if patterns[:4]!=['ORACLE_ALL_ACCEPT','ORACLE_REJECT_0','ORACLE_REJECT_3','ORACLE_REJECT_1']:raise ValueError('all/first/middle/last coverage incomplete')
        for i,row in enumerate(value['iterations']):
            candidate=a.directory/f'iter-{i}-observed.logits.f32';raw=candidate.read_bytes()
            if len(raw)!=8*201088*4 or not np.isfinite(np.frombuffer(raw,dtype='<f4')).all():raise ValueError('complete finite candidate rows missing')
            for known in range(row['known_rows'],row['feature_row']+2):
                ref=(a.directory/f'iter-{i}-ref-known-{known}.logits.f32').read_bytes()
                if len(ref)!=len(raw) or not np.isfinite(np.frombuffer(ref,dtype='<f4')).all() or raw[:known*201088*4]!=ref[:known*201088*4]:raise ValueError('rollback/continuation differs from independent prefix-only full-logit reference')
        r['raw_prefix_only_bitwise_checked']=True
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(r['status'])

if __name__=='__main__':main()
