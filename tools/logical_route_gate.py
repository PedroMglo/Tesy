"""Prospective per-layer routing policy; historical C280/C270 gates untouched."""
import argparse,json,statistics,math
from pathlib import Path
from r2_causal_gate import inspect as inspect_cost,METRICS
from block_layer_reuse_gate import inspect as inspect_capture
from run_bounded import sha256

def numeric(root,reference,fixture):
    a=inspect_capture(root,fixture,'r2-reuse');b=inspect_capture(reference,fixture,'r2-reuse')
    if a['stage_payloads']!=b['stage_payloads'] or a['native_argmax_ids']!=b['native_argmax_ids']:
        raise ValueError('FAIL_SAME_PROFILE_LOGICAL_ROUTE_STAGES_LOGITS')
    return {'status':'PASS_SELECTED_LOGICAL_ROUTE_BYTES_STAGES_LOGITS','full_layer_stages':216,'full_logits':7,'consumer_components':a['consumer_components'],'initial_state_equality_required':False,'reason':'Own policy prefix from start; same numeric profile; not cache-state equality','scope':'warm153 + six supplied decode tokens, selected consumer bytes; no universal correctness'}

def evaluate(directory):
    p=json.loads((directory/'protocol.json').read_text());runs=p['runs']
    if len(runs)!=8 or [(r['case'],r['policy']) for r in runs]!=[(c,q) for c in ['nominal153','code153'] for q in ['OLD','LOGICAL','LOGICAL','OLD']]:raise ValueError('exact ABBA/cardinality required')
    if len({r['id'] for r in runs})!=8 or len({r['command'][4] for r in runs})!=8:raise ValueError('duplicate ID/root')
    cases={};rows=[]
    for r in runs:
        fixture=json.loads(Path(r['command'][2]).read_text())[r['case']]
        v,h=inspect_cost(r['command'][4],fixture,'E',r['case']);l=json.loads((Path(r['command'][4])/'logical-policy.json').read_text())
        enabled=r['policy']=='LOGICAL'
        if l['enabled']!=enabled or [x['layer'] for x in l['layers']]!=list(range(36)):raise ValueError('policy/layer identity absent')
        if enabled:
            for x in l['layers']:
                expected=len(fixture['ids'])+32 if x['layer']!=35 else 41
                if x['rows']!=expected or x['decay_epoch']!=expected//64 or x['lifecycle']!=1 or x['sequence']!=0 or x['accounted_rows']!=len(x['last_positions']):raise ValueError('logical routing event accounting mismatch')
        else:
            if any(x['rows'] or x['event_serial'] for x in l['layers']):raise ValueError('old policy mutated logical state')
        rows.append({'id':r['id'],'policy':r['policy'],'case':r['case'],'metrics':{k:v[k] for k in METRICS},'full_logits_sha256':h})
        cases.setdefault(r['case'],[]).append((v,h))
    reports={}
    for case,x in cases.items():
        if len({h for _,h in x})!=1:raise ValueError('FAIL_SAME_PROFILE_FULL33_LOGITS')
        pairs=[]
        for a,b in [(0,1),(3,2)]:pairs.append({'arms':[rows[(0 if case=='nominal153' else 4)+a]['id'],rows[(0 if case=='nominal153' else 4)+b]['id']],'gain_percent':{k:100*(x[a][0][k]-x[b][0][k])/x[a][0][k] for k in METRICS}})
        reports[case]={'pairs':pairs,'median_paired_gain_percent':{k:statistics.median(q['gain_percent'][k] for q in pairs) for k in METRICS}}
    passed=all(all(q['gain_percent']['total_s']>0 for q in v['pairs']) and v['median_paired_gain_percent']['decode32_s']>=-5 for v in reports.values())
    return {'status':'GO_LOGICAL_ROUTE_POLICY_CANDIDATE' if passed else 'NO_GO_LOGICAL_ROUTE_POLICY_COST','rows':rows,'cases':reports,'scope':'E same numerical profile/own-policy prefix; supplied153+32; contemporary R0 promotion NOT_RUN'}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('directory',type=Path);a.add_argument('--numeric',action='store_true');a.add_argument('--reference',type=Path);a.add_argument('--fixture',type=Path);a.add_argument('--arm-policy',choices=['OLD','LOGICAL']);a.add_argument('--case');a.add_argument('--expected-logits-sha256');a.add_argument('--output',type=Path,required=True);v=a.parse_args()
    if v.arm_policy:
        fixture=json.loads(v.fixture.read_text())[v.case];data,h=inspect_cost(v.directory,fixture,'E',v.case)
        observed_path=v.directory/'prefill-end-nondraining.json'
        observed=json.loads(observed_path.read_text()) if observed_path.exists() else None
        if observed:
            if observed['n_calls']!=data['initial']['n_calls']+36:raise ValueError('E prefill call boundary differs')
            elapsed=observed['observer_s']
            if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=.03*data['decode32_s']:raise ValueError('metadata observer exceeds prospective3% phase allowance')
        if h!=v.expected_logits_sha256:raise ValueError('FAIL_SAME_PROFILE_FULL33_LOGITS_REFERENCE')
        r={'status':'PASS_LOGICAL_ROUTE_COST_ARM','policy':v.arm_policy,'full_logits_sha256':h,'metadata_copy_s':observed['observer_s'] if observed else None,'observed_prefill_end_calls':observed['n_calls'] if observed else None,'null_reason':None if observed else 'NOT_RUN_NO_INTERMEDIATE_OBSERVER_IN_COST_WINDOW','metrics':{k:data[k] for k in METRICS},'scope':'Provided native IDs, own-policy prefix; no generated throughput'}
    else:
        r=numeric(v.directory,v.reference,json.loads(v.fixture.read_text())['anchor-nominal153']) if v.numeric else evaluate(v.directory)
    with v.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(r['status'])
