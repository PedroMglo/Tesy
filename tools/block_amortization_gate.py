"""Strict complete-output equal-input A1 timing and paired economic gate."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from block_verifier_contract import paired_gain,budgets
from c94_session_wave_8k_reference import tree_digest


def integer_ids(value,number):
    return isinstance(value,list) and len(value)==number and all(type(x)is int and 0<=x<201088 for x in value)


def inspect_run(root,fixture,case,B,mode):
    root=Path(root);spec=json.loads(Path(fixture).read_text())[case];out=json.loads((root/'result.json').read_text())
    size=1 if mode=='ar' else B
    if mode not in ('ar','block') or out.get('status')!='MEASURED_CONTROLLED_COMPLETE_OUTPUT_PATH' or out.get('mode')!=mode or out.get('B')!=B or out.get('case')!=case:
        raise ValueError('wrong native profile/complete output receipt')
    if out.get('official_prefix_ids')!=spec['ids'] or out.get('native_teacher_forced_inputs')!=spec['continuation_ids'][:32] or not integer_ids(out.get('native_argmax_ids'),32):
        raise ValueError('official input/native continuation/output IDs incomplete or wrong')
    if out.get('positions')!=32 or out.get('complete_logit_rows')!=32 or out.get('calls')!=32//size or out.get('ideal_L')!=32 or out.get('D_assumed_s')!=0 or out.get('R_assumed_s')!=0:
        raise ValueError('all rows/anchor/call accounting invalid')
    if mode=='ar' and out['native_argmax_ids']!=spec['continuation_ids'][1:33]:
        raise ValueError('R0 clean native continuation no longer matches frozen control')
    wall=out.get('wall_s');paired_gain(wall,wall)
    routes=out.get('authoritative_union_by_call_layer',[])
    if len(routes)!=32//size or any(len(call)!=36 for call in routes):raise ValueError('missing authoritative unions by call/layer')
    if any(not isinstance(ids,list) or not 1<=len(ids)<=min(128,size*4) or len(set(ids))!=len(ids) or any(type(x)is not int or not 0<=x<128 for x in ids) for call in routes for ids in call):
        raise ValueError('invalid authoritative expert union')
    initial=json.loads((root/'initial-residency.json').read_text());final=json.loads((root/'final-residency.json').read_text())
    if len(initial.get('layers',[]))!=36 or len(final.get('layers',[]))!=36 or initial.get('pending_queue')!=0 or final.get('pending_queue')!=0:
        raise ValueError('full expert state or bounded drain absent')
    if final['n_calls']-initial['n_calls']!=36*(32//size):raise ValueError('missing/extra executed native layer calls')
    if final['n_waves']!=initial['n_waves'] or final['n_preload']!=initial['n_preload']:
        raise ValueError('unexpected timing wave/preload regime')
    tiers={};load_sum=0
    for old,new in zip(initial['layers'],final['layers']):
        if old['layer']!=new['layer'] or len(old['slot_generation'])!=40 or len(new['slot_generation'])!=40 or any(old['slot_claimed']) or any(new['slot_claimed']) or 1 in old['slot_state'] or 1 in new['slot_state']:
            raise ValueError('slot/generation/worker state invalid')
        delta=sum(new['slot_generation'])-sum(old['slot_generation'])
        if delta<0:raise ValueError('negative native reservations')
        if old['logical_bytes_per_load']!=new['logical_bytes_per_load']:raise ValueError('native weight byte plan changed')
        tier=old['native_cache_buffer'];tiers.setdefault(tier,{'loads':0,'logical_bytes':0});tiers[tier]['loads']+=delta;tiers[tier]['logical_bytes']+=delta*old['logical_bytes_per_load'];load_sum+=delta
    if load_sum!=final['n_miss']-initial['n_miss']:raise ValueError('reservation/load counter inconsistency')
    clean_initial={k:initial[k] for k in ('layers','pending_queue','n_calls')}
    return dict(case=case,mode=mode,contrast_B=B,native_B=size,positions=32,calls=32//size,wall_s=wall,
                per_position_s=wall/32,all_logits_rows=32,native_argmax_ids=out['native_argmax_ids'],
                initial=clean_initial,initial_sha256=hashlib.sha256(json.dumps(clean_initial,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                logical_loads_by_cache_tier=tiers,wait_union_s=(final['stall_us']-initial['stall_us'])/1e6,
                raw_tree=tree_digest(root),scope='Complete-output controlled fixed native inputs, not confirmed token production or physical NVMe traffic')


def evaluate(case_rows,B):
    if B not in (2,4,8) or len(case_rows)!=3 or len({x['case'] for x in case_rows})!=3:raise ValueError('exact three classes required')
    result=[]
    for group in case_rows:
        arms=group['arms']
        if len(arms)!=4 or [x['mode'] for x in arms]!=['ar','block','block','ar'] or any(x['case']!=group['case'] or x['contrast_B']!=B for x in arms):raise ValueError('exact ordered ABBA profiles/classes required')
        pairs=[]
        for ai,bi in ((0,1),(3,2)):
            a,b=arms[ai],arms[bi]
            if a['initial']!=b['initial']:raise ValueError('initial complete expert residency/eviction state differs; not KV-only comparable')
            gain=paired_gain(a['wall_s'],b['wall_s']); per_verify=b['wall_s']/(32/B)
            margins=[budgets(a['wall_s']/32*B,B,per_verify,accepted=L,draft_s=0,rollback_s=0,gain=.15) for L in range(1,B+1)]
            pairs.append({'control_s':a['wall_s'],'block_s':b['wall_s'],'gain_percent':gain,'V_B_s':per_verify,'T_AR_s':a['wall_s']/32,'D_R_assumed_s':0,'margins_L1_to_B':margins,
                          'cross_shape_argmax_equal':sum(x==y for x,y in zip(a['native_argmax_ids'],b['native_argmax_ids'])),'argmax_rows':32})
        gains=[p['gain_percent'] for p in pairs]; med=median(gains)
        median_margins=[median(p['margins_L1_to_B'][L-1]['D_budget_s'] for p in pairs) for L in range(1,B+1)]
        good=med>=15 and all(x>0 for x in gains) and median_margins[-1]>0
        result.append({'case':group['case'],'pairs':pairs,'median_paired_gain_percent':med,'economic_class_GO':good,'median_D_budget_s_L1_to_B':median_margins})
    development=[x for x in result if x['case']!='anchor-nominal153']
    go=len(development)==2 and all(x['economic_class_GO'] for x in development)
    return {'status':'GO_A1_COMPLETE_BLOCK_AMORTIZATION' if go else 'NO_GO_A1_COMPLETE_BLOCK_MARGIN_IN_SCOPE','B':B,'K':B-1,'classes':result,
            'scope':'Perfect assist D0/Rideal, full logits/materialization and greedy finite checks; economic screen not acceptance/product utility. R1 semantic coverage separately mandatory.',
            'R0_vs_R1':'Report native argmax disagreements and full-logit differences separately; fixed-prefix R1 qualified on selected coverage, no stochastic claim'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--run-root',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--case');p.add_argument('--B',type=int);p.add_argument('--mode');p.add_argument('--paired-root',type=Path);a=p.parse_args()
    if a.run_root:
        r=inspect_run(a.run_root,a.fixture,a.case,a.B,a.mode)
        if a.paired_root:
            paired=inspect_run(a.paired_root,a.fixture,a.case,a.B,'block' if a.mode=='ar' else 'ar')
            if paired['initial']!=r['initial']:raise ValueError('paired initial complete expert state differs; preserve both raw and suspend this contrast')
        target=a.run_root.parent/(a.run_root.name+'.timing-summary.json')
    else:
        proto=json.loads((a.directory/'protocol.json').read_text());rows=[]
        for case in proto['timing_contract']['case_order']:
            arms=[]
            for run in proto['runs']:
                if run['case']==case:
                    arms.append(json.loads((a.directory/'raw'/(run['id']+'.native.timing-summary.json')).read_text()))
            rows.append({'case':case,'arms':arms})
        r=evaluate(rows,proto['timing_contract']['B']);target=a.directory/'amortization-summary.json'
    with target.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':r.get('status','VALIDATED_NATIVE_EQUAL_INPUT_TIMING'),'path':str(target)}))
