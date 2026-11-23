"""Fixed learned revision investment gate; no integrated latency claim."""
import argparse,json,math
from pathlib import Path
import numpy as np
from expert_score_calibration_gate import native
from expert_primary_state_replay import PrimaryState
from expert_prediction_holdout_gate import prefix_arm,prefix_events,extract_prefix
from expert_prediction_holdout_scenario import evaluate
from expert_native_stage_scenario import simulate_native

def reconstructed_records(root,native_result):
    root=Path(root);v=json.loads((root/'result.json').read_text());n=v['decode_calls']
    rows=prefix_events(root/'events.tsv',True,n);old=json.loads((root/'estimator.json').read_text())['records']
    times={(r['call'],r['layer']):r['us'] for r in rows if r['kind']==1}
    initial=json.loads((root/'initial.json').read_text());reference=PrimaryState(initial,rows)
    for r in old:
        reference.advance(times[r['call'],r['source_layer']]+r['complete_predictor_us'])
        if reference.selected(r['target_layer'],r['prediction_ids'])!=r['available_primary_state']:
            raise ValueError('existing observed primary state reconstruction mismatch')
    reference.final(v['final'])
    actual=PrimaryState(initial,rows);new=[]
    for i,r in enumerate(old):
        pid=native_result['native_top4'][i*4:i*4+4]
        dt=r['complete_predictor_us']+native_result['cost_us'][i]
        if not math.isfinite(dt) or dt<=0:raise ValueError('complete learned predictor cost')
        finish=times[r['call'],r['source_layer']]+dt
        router=[e['us'] for e in rows if e['kind']==2 and e['call']==r['call'] and e['layer']==r['target_layer']]
        if len(router)!=1 or finish>=router[0]:raise ValueError('isolated predictor cost exceeds observed feature window')
        actual.advance(finish)
        new.append({'call':r['call'],'source_layer':r['source_layer'],'target_layer':r['target_layer'],
                    'prediction_ids':pid,'available_primary_state':actual.selected(r['target_layer'],pid),
                    'complete_predictor_us':dt})
    actual.final(v['final'])
    return new,{'existing_queries_checked':len(old)*4,'existing_state_mismatches':0,'all_final_layers_equal':True,
                'assumption':'Reserve/commit metadata source-audited and reconstructed at historical feature time + measured original cost + isolated affine cost. Fixed original cache evolution; changed physical concurrency not predicted. LOADING never treated as ready or free.'}

def analysis(protocol):
    old=json.loads(Path(protocol['heldout_protocol']).read_text());fixture=json.loads(Path(old['fixture']).read_text());weights=Path(protocol['weights'])
    out={'classification':'ESTIMADO','predictor_heldout':True,'training':True,'actual_byte_staging':False,'cases':{},
         'assumptions':['Whole-conversation eight-task fit, no development/heldout labels or outcomes used in fit/statistics',
                        'Actual native CPU8 affine costs added to previous original approximation/copy/sort costs; isolated CPU cache/contending target may change them',
                        'Original OFF demands/services/cache fixed; false reads use per-layer median and sensitivity .8/1/1.2',
                        'C305 worker occupancy, queued forecast fallback, arena ten entries, max3 unconfirmed reads and stage finish included',
                        'Original arithmetic/greedy prefixes retained. Native mutex/bookkeeping and service changes under forecast contention remain unknown; canary only, no promotion']}
    for case in ('heldout-intervals','heldout-inventory'):
        a,b=[r for r in old['runs'] if r.get('case')==case];aroot,broot=Path(a['command'][4]),Path(b['command'][4])
        av=prefix_arm(aroot,fixture[case],case,False);bv=prefix_arm(broot,fixture[case],case,True,aroot)
        nr=Path(protocol['native_outputs'][case]);nv=native(nr,weights,broot)
        records,replay=reconstructed_records(broot,nv)
        data=extract_prefix(prefix_events(aroot/'events.tsv',True,av['decode_calls']),av['decode_calls'])
        v={'control':av,'uncalibrated_capture':bv,'investment_window_valid':av['investment_window_valid'] and bv['investment_window_valid'],
           'native_calibration':nv,'primary_state_reconstruction':replay,'sensitivity':[]}
        for scale in (.8,1.,1.2):
            base=simulate_native(data,[],scale,128*2**20);pred=simulate_native(data,records,scale,128*2**20)
            pred['gain_percent']=100*(base['decode_us']-pred['decode_us'])/base['decode_us']
            v['sensitivity'].append({'service_scale':scale,'baseline':base,'prediction':pred})
        truth={(e['call'],e['layer']):set() for e in prefix_events(broot/'events.tsv',True,av['decode_calls']) if e['kind']==3 and e['call']>0 and 2<=e['layer']<=24}
        missing={k:set() for k in truth}
        for e in prefix_events(broot/'events.tsv',True,av['decode_calls']):
            key=e['call'],e['layer']
            if e['kind']==3 and key in truth:
                truth[key].add(e['expert'])
                if e['bytes']!=2:missing[key].add(e['expert'])
        demand=hit=issued=right=0
        for r in records:
            m=missing[r['call'],r['target_layer']];forecasts={x['expert'] for x in r['available_primary_state'] if x['state']==0}
            demand+=len(m);hit+=len(m&set(r['prediction_ids']));issued+=len(forecasts);right+=len(m&forecasts)
        v['missing_demand_recall']=hit/demand if demand else None;v['issued_precision']=right/issued if issued else None
        out['cases'][case]=v
    out['decision']=evaluate(out['cases'])
    if not out['decision']['admitted_scopes']:out['decision']['status']='NO_GO_FIXED_AFFINE_HELDOUT_NATIVE_SERVICE_SCENARIO'
    else:out['decision']['status']='GO_BOUNDED_LEARNED_STAGING_CANARY'
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('protocol',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=analysis(json.loads(a.protocol.read_text()))
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['decision']['status'])
if __name__=='__main__':main()
