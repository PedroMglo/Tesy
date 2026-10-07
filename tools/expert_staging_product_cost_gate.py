"""Owner post-C282 global/phase cost gates on contemporary trace-OFF R0/stage."""
import argparse,json,math,statistics
from pathlib import Path
from r2_causal_gate import initial_identity,METRICS
from block_prefill_timing_gate import loads
from expert_staging_cost_gate import cost_arm

def paired(rows):
    if len(rows)!=4 or [x.get('staging_enabled') for x in rows]!=[False,True,True,False] or any(x.get('trace') is not False for x in rows):raise ValueError('exact production ABBA required')
    for r in rows:
        for k in METRICS:
            v=r.get(k)
            if type(v) not in (int,float) or not math.isfinite(v) or v<=0:raise ValueError('finite positive measured clock required')
        if not math.isclose(r['total_s'],r['prefill153_s']+r['decode32_s'],abs_tol=1e-8):raise ValueError('total clock mismatch')
    pairs=[]
    for ai,bi in ((0,1),(3,2)):
        a,b=rows[ai],rows[bi]
        if initial_identity(a)!=initial_identity(b) or a['native_argmax_ids']!=b['native_argmax_ids']:raise ValueError('initialcache/policy or sameprofile outputrows differ')
        pairs.append({'control_arm':ai+1,'candidate_arm':bi+1,'gain_percent':{k:100*(a[k]-b[k])/a[k] for k in METRICS},'primary_generations_control':loads(a),'primary_generations_candidate':loads(b),'stage_stats_candidate':b['stage_stats'],'scope':'Logicalprimarygenerations/providedwork, not physicaltraffic/confirmedoutput count.'})
    return {'pairs':pairs,'median_paired_gain_percent':{k:statistics.median(x['gain_percent'][k] for x in pairs) for k in METRICS}}

def evaluate(cases):
    if set(cases)!={'nominal153','code153'}:raise ValueError('both frozen production cases required')
    report={c:paired(rows) for c,rows in cases.items()};global_cases=[];phase=[]
    for c,r in report.items():
        m=r['median_paired_gain_percent'];p=r['pairs'];other=report['code153' if c=='nominal153' else 'nominal153']['median_paired_gain_percent']
        total=m['total_s']>=8 and all(x['gain_percent']['total_s']>0 for x in p)
        decode=m['decode32_s']>=15 and m['total_s']>0 and all(x['gain_percent']['decode32_s']>0 for x in p)
        if (total or decode) and other['total_s']>=-5:global_cases.append(c)
        for target,protection in [('prefill153_s','decode32_s'),('decode32_s','prefill153_s')]:
            if m[target]>=10 and all(x['gain_percent'][target]>0 for x in p) and m['total_s']>0 and m[protection]>=-5 and other['total_s']>=-5:phase.append({'case':c,'phase':target})
    return {'status':'GO_REAL_STAGING_INTEGRATED_COST' if global_cases else 'PHASE_SURVIVOR_REAL_STAGING_COST' if phase else 'NO_GO_REAL_STAGING_INTEGRATED_COST','global_qualified_cases':global_cases,'phase_survivor':phase,'cases':report,'scope':'Real4worker originalbyte forecast/predictor/read/copy/cancellationcleanup included. Same supplied153+32/nativeR0full33reference. No newnaturalresponse, usefulgain/preset/M4 or physicalNVMe/energy claim. No replacement/retry because variance.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();protocol=json.loads((a.directory/'protocol.json').read_text());runs=protocol['runs']
    if len(runs)!=8 or [(r.get('case'),r.get('stage'),r.get('trace')) for r in runs]!=[(c,on,False) for c in ('nominal153','code153') for on in (False,True,True,False)] or len({r['id'] for r in runs})!=8 or len({r['command'][4] for r in runs})!=8:raise ValueError('exact8orderedproductionarms/IDs/roots')
    cases={};hashes={}
    for r in runs:
        cmd=r['command'];c=r['case'];fixture=json.loads(Path(cmd[2]).read_text())[c];v,out=cost_arm(cmd[4],fixture,c,r['stage'],False,protocol['expected_full_logits_sha256'][c]);v['stage_stats']=out['stage_stats'];cases.setdefault(c,[]).append(v);hashes.setdefault(c,[]).append(out['full33_logits_sha256'])
    out=evaluate(cases);out['full33_logits_sha256']=hashes
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])
if __name__=='__main__':main()
