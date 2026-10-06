"""Task-disjoint untrained estimator investment gate; no physical prefetch gain."""
import argparse, json, math
from pathlib import Path
from expert_prediction_holdout_gate import prefix_arm, prefix_events, extract_prefix
from expert_prediction_scenario import simulate
from expert_real_prediction_scenario import simulate_real

def evaluate(cases):
    if list(cases)!=['heldout-intervals','heldout-inventory']:
        raise ValueError('exact two frozen heldout cases')
    gains={}
    for case,v in cases.items():
        if not v['investment_window_valid']:
            return {'status':'INCONCLUSIVE_PARTIAL_NATIVE_PREFIX','admitted_scopes':[],
                    'reason':'At least one actual EOS prefix has fewer than16 forwards; no imputed score'}
        sensitivity=v['sensitivity']
        if [z['service_scale'] for z in sensitivity]!=[.8,1.,1.2]:raise ValueError('exact sensitivity')
        for z in sensitivity:
            b=z['baseline']['decode_us'];p=z['prediction']['decode_us'];g=z['prediction']['gain_percent']
            if any(type(x) not in (int,float) or not math.isfinite(x) for x in (b,p,g)) or min(b,p)<=0:
                raise ValueError('finite scenario clocks')
            if not math.isclose(g,100*(b-p)/b,rel_tol=1e-10,abs_tol=1e-8):raise ValueError('derived gain')
            if z['prediction']['staging_peak_bytes']>128*2**20:raise ValueError('staging bandwidth/arena model violated')
        gains[case]=sensitivity[1]['prediction']['gain_percent']
    scopes=[c for c,g in gains.items() if g>=10 and all(other>=-5 for other in gains.values())]
    return {'status':'GO_BOUNDED_REAL_STAGING_CANARY' if scopes else 'NO_GO_UNTRAINED_ESTIMATOR_HELDOUT_SCENARIO',
            'admitted_scopes':scopes,'service_scale1_gain_percent':gains,
            'scope':'Conditional investment only. No byte staging or latency improvement measured. Costs of integrated staging lookup/coordination still require real canary.'}

def main():
    a=argparse.ArgumentParser();a.add_argument('directory',type=Path);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    protocol=json.loads((args.directory/'protocol.json').read_text());runs=protocol['runs'];fixture=json.loads(Path(protocol['fixture']).read_text())
    order=[(c,e) for c in ('heldout-intervals','heldout-inventory') for e in (False,True)]
    if len(runs)!=4 or [(r['case'],r['estimate']) for r in runs]!=order or len({r['id'] for r in runs})!=4 or len({r['command'][4] for r in runs})!=4:raise ValueError('exact ordered independent arms')
    result={'classification':'ESTIMADO','training':False,'predictor_heldout':True,'staged_bytes_in_actual_model':0,'cases':{},
            'assumptions':['Original observed OFF missing-generation stream and fixed compute, primary cache not resimulated',
            'Real ON earlier residual top4 and complete measured costs; no oracle issuing future IDs',
            'False experts use destination-layer median three-read service; .8/1/1.2 sensitivity',
            'Four nonpreemptible workers with at most3 speculative reads; demand priority, original demand copies after authority',
            '128MiB arena includes in-flight/ready data, queued expiry avoids read but running reads cannot be undone',
            'Integrated staging lookup/mutex/copy overhead unmeasured; actual service/compute can change under contention',
            'At most32 nativegreedy forwards per new conversation, not completed functional task or quality confirmation']}
    for c in ('heldout-intervals','heldout-inventory'):
        off,on=[r for r in runs if r['case']==c];aroot,broot=Path(off['command'][4]),Path(on['command'][4])
        av=prefix_arm(aroot,fixture[c],c,False);bv=prefix_arm(broot,fixture[c],c,True,aroot)
        v={'control':av,'estimator':bv,'investment_window_valid':av['investment_window_valid'] and bv['investment_window_valid'],
           'raw':{'control':str(aroot),'estimator':str(broot)},'sensitivity':[]}
        if v['investment_window_valid']:
            data=extract_prefix(prefix_events(aroot/'events.tsv',True,av['decode_calls']),av['decode_calls'])
            records=json.loads((broot/'estimator.json').read_text())['records']
            for scale in (.8,1.,1.2):
                baseline=simulate(data,None,scale,128*2**20);prediction=simulate_real(data,records,scale,128*2**20)
                prediction['scope']='Heldout conditional scenario with fixed OFF observed services/cache demands; not physical improvement'
                prediction['gain_percent']=100*(baseline['decode_us']-prediction['decode_us'])/baseline['decode_us']
                v['sensitivity'].append({'service_scale':scale,'baseline':baseline,'prediction':prediction})
        result['cases'][c]=v
    result['decision']=evaluate(result['cases'])
    with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(result['decision']['status'])
if __name__=='__main__':main()
