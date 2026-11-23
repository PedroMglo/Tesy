"""Prospective same-profile R0 layout cost, original historical evaluators unchanged."""
import argparse,json,math,statistics
from pathlib import Path
from r2_causal_gate import inspect,initial_identity,validate,METRICS
from block_prefill_timing_gate import loads
TRANSPORT=('ORIGINAL','EXPERT_CONTIGUOUS')

def transport(v,kind):
    if kind not in TRANSPORT or v.get('transport')!=kind:raise ValueError('transport identity mismatch')
    count=v.get('store_loads_complete');size=v.get('store_logical_weight_bytes')
    if type(count) is not int or type(size) is not int or count<0 or size!=count*13219200:
        raise ValueError('store actual completed authoritative load accounting invalid')
    if kind=='ORIGINAL':
        if count!=0 or v.get('store_manifest_env') is not None:raise ValueError('control unexpectedly uses store')
    elif count<=0 or not isinstance(v.get('store_manifest_env'),str) or not v['store_manifest_env']:
        raise ValueError('candidate real store consumption absent')
    return v

def paired(rows):
    if len(rows)!=4 or [x.get('transport') for x in rows]!=[TRANSPORT[0],TRANSPORT[1],TRANSPORT[1],TRANSPORT[0]]:
        raise ValueError('exact transport ABBA cardinality required')
    pairs=[]
    for ai,bi in ((0,1),(3,2)):
        a,b=rows[ai],rows[bi]
        if initial_identity(a)!=initial_identity(b):raise ValueError('complete initial experts/policy state differs')
        if a['native_argmax_ids']!=b['native_argmax_ids']:raise ValueError('same-profile native row argmax differs')
        pairs.append({'control_arm':ai+1,'candidate_arm':bi+1,'gain_percent':{k:100*(a[k]-b[k])/a[k] for k in METRICS},'loads_control':loads(a),'loads_candidate':loads(b)})
    return {'pairs':pairs,'median_paired_gain_percent':{k:statistics.median(x['gain_percent'][k] for x in pairs) for k in METRICS}}

def evaluate(cases):
    if set(cases)!={'nominal153','code153'}:raise ValueError('both exact frozen cases required')
    report={c:paired(rows) for c,rows in cases.items()}
    qualified=[];phase=[]
    for c,r in report.items():
        m=r['median_paired_gain_percent'];p=r['pairs'];other=report['code153' if c=='nominal153' else 'nominal153']['median_paired_gain_percent']
        total=m['total_s']>=8 and all(x['gain_percent']['total_s']>0 for x in p)
        decode=m['decode32_s']>=15 and m['total_s']>0 and all(x['gain_percent']['decode32_s']>0 for x in p)
        if (total or decode) and other['total_s']>=-5:qualified.append(c)
        for target,protection in [('prefill153_s','decode32_s'),('decode32_s','prefill153_s')]:
            if m[target]>=10 and all(x['gain_percent'][target]>0 for x in p) and m['total_s']>0 and m[protection]>=-5 and other['total_s']>=-5:phase.append({'case':c,'phase':target})
    return {'status':'GO_INTEGRATED_EXPERT_SERVICE_COST' if qualified else 'PHASE_SURVIVOR_EXPERT_SERVICE' if phase else 'NO_GO_INTEGRATED_EXPERT_SERVICE_COST','global_qualified_cases':qualified,'phase_survivor':phase,'cases':report,'scope':'Same supplied153+32 native work/full33 finite rows, original R0 profile. Logical generation/bytes are not physical NVMe traffic or generated/confirmed throughput. No useful final/endpoint or M4 claim.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--case');p.add_argument('--transport',choices=TRANSPORT);p.add_argument('--expected-logits-sha256');p.add_argument('--family',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.family:
        protocol=json.loads((a.directory/'protocol.json').read_text());runs=protocol['runs']
        expected=[(c,t) for c in ('nominal153','code153') for t in (TRANSPORT[0],TRANSPORT[1],TRANSPORT[1],TRANSPORT[0])]
        if len(runs)!=8 or [(r.get('case'),r.get('transport')) for r in runs]!=expected or len({r['id'] for r in runs})!=8 or len({r['command'][4] for r in runs})!=8:raise ValueError('exact ordered family/unique IDs/roots required')
        cases={};hashes={}
        for r in runs:
            cmd=r['command'];c=r['case'];t=r['transport']
            if len(cmd)!=7 or cmd[3]!=c or cmd[5:]!=['R0','v1']:raise ValueError('native call/profile command contract')
            fixture=json.loads(Path(cmd[2]).read_text())[c];v,h=inspect(cmd[4],fixture,'R0',c);transport(v,t)
            if h!=protocol['expected_full_logits_sha256'][c]:raise ValueError('same-profile full logits differ from reusable original native reference')
            cases.setdefault(c,[]).append(v);hashes.setdefault(c,[]).append(h)
        out=evaluate(cases);out['full33_logits_sha256']=hashes
    else:
        fixture=json.loads(a.fixture.read_text())[a.case];v,h=inspect(a.directory,fixture,'R0',a.case);transport(v,a.transport)
        if h!=a.expected_logits_sha256:raise ValueError('same-profile full33 native logits differ')
        out={'status':'PASS_SAME_PROFILE_R0_TRANSPORT_COST_ARM','transport':a.transport,'case':a.case,'metrics':{k:v[k] for k in METRICS},'loads':loads(v),'full_logits_sha256':h,'native_argmax_ids':v['native_argmax_ids'],'store_loads_complete':v['store_loads_complete'],'store_logical_weight_bytes':v['store_logical_weight_bytes']}
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])
if __name__=='__main__':main()
