"""Original-gate movement estimator capture. No implicit predictor promotion."""
import argparse,json,math
from pathlib import Path
import numpy as np
from expert_service_window_gate import arm

def inspect_estimator(root,fixture,case,on,expected):
    root=Path(root);v,h,events=arm(root,fixture,case,True,expected)
    meta=json.loads((root/'estimator.json').read_text())
    if meta.get('schema')!='original-destination-gate-on-earlier-residual-v1' or meta.get('enabled') is not on or meta.get('training') is not False or meta.get('source_horizon')!=2 or meta.get('CPU_backend_threads')!=8 or not 0<meta.get('capture_bytes',0)<=64*2**20:raise ValueError('estimator scope/identity/cap')
    def load(name,n):
        p=root/name
        if p.stat().st_size!=n*4:raise ValueError('truncated array '+name)
        x=np.fromfile(p,dtype='<f4')
        if not np.isfinite(x).all():raise ValueError('nonfinite array '+name)
        return x
    gt=load('true-routing-scores.f32',32*23*128).reshape(32,23,128)
    records=meta['records'];true={}
    for e in events:
        if e['kind']==3 and e['call']>0 and 2<=e['layer']<=24:true.setdefault((e['call'],e['layer']),[]).append(e)
    if len(true)!=32*23 or any(len(x)!=4 for x in true.values()):raise ValueError('true labels omitted')
    if not on:
        if records or (root/'earlier-input.f32').exists() or (root/'prediction-scores.f32').exists():raise ValueError('OFF unexpectedly forecasts')
        return {'status':'PASS_ORIGINAL_ESTIMATOR_OFF','full33_logits_sha256':h,'case':case,'native_timings':{k:v[k] for k in ('prefix_s','prefill153_s','decode32_s','total_s')}}
    inputs=load('earlier-input.f32',32*23*2880).reshape(32,23,2880)
    scores=load('prediction-scores.f32',32*23*128).reshape(32,23,128)
    if [(x.get('call'),x.get('source_layer'),x.get('target_layer')) for x in records]!=[(c,l,l+2) for c in range(1,33) for l in range(23)]:raise ValueError('exact ordered prediction coverage')
    hit=missing=forecast=correct_forecast=resident_hit=0;cost=0.
    for x in records:
        c,l=x['call'],x['target_layer'];pids=x['prediction_ids'];states=x['available_primary_state']
        if len(pids)!=4 or len(set(pids))!=4 or any(type(i) is not int or not 0<=i<128 for i in pids):raise ValueError('prediction IDs')
        ranked=np.argsort(-scores[c-1,l-2],kind='stable')[:4].tolist()
        if pids!=ranked or len(states)!=4 or [s['expert'] for s in states]!=pids:raise ValueError('score/ranking/state identity')
        dt=x['complete_predictor_us']
        if type(dt) not in (int,float) or not math.isfinite(dt) or dt<=0:raise ValueError('invalid predictor clock')
        cost+=dt
        absent={e['expert'] for e in true[c,l] if e['bytes']!=2}
        for s in states:
            if s['state'] not in (0,1,2) or (s['state']==0 and (s['slot']!=-1 or s['generation']!=0)) or (s['state']!=0 and (not 0<=s['slot']<40 or s['generation']<=0)):raise ValueError('observed primary state missing')
        issued={s['expert'] for s in states if s['state']==0}
        missing+=len(absent);hit+=len(absent&set(pids));forecast+=len(issued);correct_forecast+=len(absent&issued)
        resident_hit+=len({e['expert'] for e in true[c,l] if e['bytes']==2}&set(pids))
    weights=json.loads((root/'original-auxiliary-tensors.json').read_text())
    if len(weights['weights'])!=23*3:raise ValueError('original auxiliary tensors incomplete')
    for w in weights['weights']:load(w['file'],w['bytes']//4)
    return {'status':'PASS_ORIGINAL_MOVEMENT_ESTIMATOR_CAPTURE','case':case,'full33_logits_sha256':h,'missing_demands':missing,'predicted_missing_hits':hit,'miss_recall':hit/missing if missing else None,'issued_speculative_reads_if_enabled':forecast,'correct_issued':correct_forecast,'issued_precision':correct_forecast/forecast if forecast else None,'predicted_resident_actual_hits_diagnostic':resident_hit,'predicted_wasted_logical_bytes_if_enabled':(forecast-correct_forecast)*13219200,'predictor_complete_seconds':cost/1e6,'native_timings':{k:v[k] for k in ('prefix_s','prefill153_s','decode32_s','total_s')},'scope':'Development only; no bytes prefetched or runtime gain claimed; captured original norm/gate/bias + current features, not trained. Actual router remains authority.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--case',required=True);p.add_argument('--on',choices=('0','1'),required=True);p.add_argument('--expected',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=inspect_estimator(a.root,json.loads(a.fixture.read_text())[a.case],a.case,a.on=='1',a.expected)
 with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
 print(v['status'])
if __name__=='__main__':main()
