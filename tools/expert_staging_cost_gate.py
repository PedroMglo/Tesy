"""Prospective real stage cost/observer boundary, no changes to historical gates."""
import argparse,json,math,statistics
from pathlib import Path
import numpy as np
from r2_causal_gate import inspect,initial_identity,METRICS
from expert_staging_gate import demand_stats
from expert_staging_forward_gate import arm as diagnostic_arm,links

def metrics(v):
    for k in ('stage_cleanup_s','decode_forward_s'):
        x=v.get(k)
        if type(x) not in (int,float) or not math.isfinite(x) or x<0:raise ValueError('pending speculative read cleanup clock missing')
    if not math.isclose(v['decode32_s'],v['decode_forward_s']+v['stage_cleanup_s'],abs_tol=1e-8):raise ValueError('cleanup excluded from measured decode')

def cost_arm(directory,fixture,case,on,trace,expected):
    directory=Path(directory);v,h=inspect(directory,fixture,'R0',case);metrics(v)
    if h!=expected or v.get('trace') is not trace or v.get('staging_enabled') is not on or v.get('estimator_enabled') is not on or v.get('diagnostic_byte_witness') is not False:raise ValueError('real source/capture/byte diagnostic/profile contract')
    s=json.loads((directory/'staging.json').read_text());st=demand_stats(s)
    if s.get('enabled') is not on or s.get('idle') is not True or s.get('fd_O_DIRECT') is not True or s.get('journal_enabled') is not trace or not 0<s.get('arena_bytes',0)+s.get('metadata_bytes',0)<=128*2**20:raise ValueError('stage arena/read/lifetime boundary')
    if st['validation_components'] or st['validation_claims']:raise ValueError('heavy canonical witness inside production timing')
    if on:
        if not (st['issued']>0 and st['completed_reads']>0 and st['consumed']>0):raise ValueError('candidate was a bypass, no actual original-byte staging')
    elif any(st.values()):raise ValueError('control did speculative work')
    meta=json.loads((directory/'estimator.json').read_text());records=meta.get('records')
    if meta.get('enabled') is not on or meta.get('training') is not False or meta.get('source_horizon')!=2 or meta.get('true_gate_capture') is not trace or meta.get('CPU_backend_threads')!=8:raise ValueError('estimator/feature identity')
    if on:
        if [(x.get('call'),x.get('source_layer'),x.get('target_layer')) for x in records]!=[(c,l,l+2) for c in range(1,33) for l in range(23)]:raise ValueError('actual predictor ordered coverage missing')
        arrays={}
        for name,n in [('earlier-input.f32',32*23*2880),('prediction-scores.f32',32*23*128)]:
            p=directory/name
            if p.stat().st_size!=n*4:raise ValueError('source feature/score array truncated')
            arrays[name]=np.fromfile(p,dtype='<f4')
            if not np.isfinite(arrays[name]).all():raise ValueError('nonfinite sourcefeature/predictor')
        scores=arrays['prediction-scores.f32'].reshape(32,23,128)
        for x in records:
            ids=x['prediction_ids'];t=x['complete_predictor_us'];state=x['available_primary_state']
            if ids!=np.argsort(-scores[x['call']-1,x['target_layer']-2],kind='stable')[:4].tolist() or any(type(i) is not int for i in ids) or type(t) not in (int,float) or not math.isfinite(t) or t<=0:raise ValueError('native predictor keys/rank/timing')
            if len(state)!=4 or [s['expert'] for s in state]!=ids or any(s['state'] not in (0,1,2) or (s['state']==0 and (s['slot']!=-1 or s['generation']!=0)) or (s['state']!=0 and (not 0<=s['slot']<40 or s['generation']<=0)) for s in state):raise ValueError('primary state absent/LOADING inventedfree')
    elif records:raise ValueError('control predicted unexpectedly')
    if trace:
        diagnostic_arm(directory,fixture,case,on,expected,False);links(directory,on)
    elif (directory/'true-routing-scores.f32').exists() or s.get('journal')!=[] or (directory/'events.tsv').read_text().splitlines()!=['kind us call route layer expert slot gen component bytes rows'] or v.get('trace_events')!=0:
        raise ValueError('trace-OFF still captured future routing/service events')
    return v,{'status':'PASS_NATIVE_STAGING_COST_ARM','case':case,'stage':on,'trace':trace,'full33_logits_sha256':h,'metrics':{k:v[k] for k in METRICS},'stage_cleanup_s':v['stage_cleanup_s'],'decode_forward_s':v['decode_forward_s'],'stage_stats':st,'claim':'Synchronized supplied-work cost. Actualstaging/predictor/cleanup included; no naturalconfirmedthroughput/energy/physicalNVMe or M4 claim.'}

def observer(cases):
    if set(cases)!={'nominal153','code153'}:raise ValueError('both observer cases required')
    out={}
    for c,rows in cases.items():
        if len(rows)!=4 or [x['trace'] for x in rows]!=[False,True,True,False] or not all(x['staging_enabled'] for x in rows):raise ValueError('exact observer candidate ABBA')
        pairs=[]
        for ai,bi in ((0,1),(3,2)):
            a,b=rows[ai],rows[bi]
            if initial_identity(a)!=initial_identity(b) or a['native_argmax_ids']!=b['native_argmax_ids']:raise ValueError('observer same-profile/initial state mismatch')
            pairs.append({k:100*(b[k]-a[k])/a[k] for k in METRICS})
        med={k:statistics.median(x[k] for x in pairs) for k in METRICS}
        out[c]={'overhead_percent_by_pair':pairs,'median_overhead_percent':med,'neutral_timing':all(med[k]<=3 for k in ('prefill153_s','decode32_s')),'interpretation':'Ifabove3%, diagnosticonly andcorrespondingtrace-OFF timings preserved. No overhead subtraction or runselection.'}
    return {'status':'PASS_SELECTED_STAGING_OBSERVER_QUALIFICATION','cases':out,'production_path':'traceOFF/true-labelOFF/journalOFF; fullrows/nativepredictions and counters retainedboundedaftertiming; nextintegratedABBA againstcontemporaryR0'}

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--case');p.add_argument('--on',choices=('0','1'));p.add_argument('--trace',choices=('0','1'));p.add_argument('--expected');p.add_argument('--observer-family',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.observer_family:
        protocol=json.loads((a.directory/'protocol.json').read_text());runs=[r for r in protocol['runs'] if not r.get('model_free')]
        if len(runs)!=8 or [(r['case'],r['trace']) for r in runs]!=[(c,t) for c in ('nominal153','code153') for t in (False,True,True,False)] or len({r['id'] for r in runs})!=8 or len({r['command'][4] for r in runs})!=8:raise ValueError('exact ordered observerfamily')
        cases={}
        for r in runs:
            cmd=r['command'];fixture=json.loads(Path(cmd[2]).read_text())[r['case']];v,_=cost_arm(cmd[4],fixture,r['case'],True,r['trace'],protocol['expected_full_logits_sha256'][r['case']]);cases.setdefault(r['case'],[]).append(v)
        out=observer(cases)
    else:
        _,out=cost_arm(a.directory,json.loads(a.fixture.read_text())[a.case],a.case,a.on=='1',a.trace=='1',a.expected)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])
if __name__=='__main__':main()
