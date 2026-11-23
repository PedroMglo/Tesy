"""Fixed learned movement revision; historical untrained gates unchanged."""
import argparse, json, math
from pathlib import Path
import numpy as np
from r2_causal_gate import inspect
from expert_staging_gate import arm as diagnostic_arm, demand_stats
from expert_staging_forward_gate import links
from expert_staging_cost_gate import cost_arm, observer
from expert_staging_product_cost_gate import validate_runs, evaluate
from expert_score_fit_gate import inspect as fit_receipt

def affine_values(root,weights,on):
    root=Path(root);weights=Path(weights);fit_receipt(weights)
    m=json.loads((weights/'manifest.json').read_text());v=json.loads((root/'estimator.json').read_text())
    if v.get('learned_movement') is not True or v.get('runtime_training') is not False or v.get('auxiliary_root')!=str(weights) or v.get('auxiliary_sha256')!=m['sha256']:raise ValueError('fixed learned identity missing')
    if not on:
        if (root/'uncalibrated-scores.f32').exists():raise ValueError('control unexpectedly evaluated affine')
        return {'status':'PASS_AUXILIARY_LOADED_CONTROL_BYPASS','weights_sha256':m['sha256']}
    def array(p,shape):
        if p.stat().st_size!=math.prod(shape)*4:raise ValueError('integrated affine array size')
        a=np.fromfile(p,dtype='<f4').reshape(shape)
        if not np.isfinite(a).all():raise ValueError('integrated affine nonfinite')
        return a.astype(np.float64)
    x=array(root/'uncalibrated-scores.f32',(32,23,128));y=array(root/'prediction-scores.f32',(32,23,128));w=array(weights/'weight.f32',(23,128,128));b=array(weights/'bias.f32',(23,128))
    eps=float(np.finfo(np.float32).eps);gamma=257*eps/(1-257*eps);maximum=0.
    for l in range(23):
        reference=x[:,l]@w[l].T+b[l];bound=gamma*(np.abs(x[:,l])@np.abs(w[l]).T+np.abs(b[l])+1.)
        error=np.abs(y[:,l]-reference)
        if (error>bound).any():raise ValueError('integrated native affine reference')
        maximum=max(maximum,float(error.max()))
    return {'status':'PASS_INTEGRATED_AUXILIARY_AFFINE_REFERENCE','maximum_error':maximum,'gamma257':gamma,'weights_sha256':m['sha256'],'scope':'Auxiliary F32 envelope, never a tolerance for target drift.'}

def arm(root,fixture,case,on,trace,witness,expected,weights):
    if witness:
        if not on or not trace:raise ValueError('byte witness requires staged trace')
        out=diagnostic_arm(root,fixture,case,on,expected,True);out.update(links(root,on));v,_=inspect(root,fixture,'R0',case)
    else:v,out=cost_arm(root,fixture,case,on,trace,expected)
    out['learned_affine']=affine_values(root,weights,on)
    if 'stage_stats' not in out:out['stage_stats']=demand_stats(json.loads((Path(root)/'staging.json').read_text()))
    return v,out

def family(directory,kind):
    d=Path(directory);p=json.loads((d/'protocol.json').read_text());runs=p['runs'];weights=Path(p['auxiliary_root']);cases={};hashes={}
    if kind=='product':validate_runs(runs)
    elif kind=='observer':
        if len(runs)!=8 or [(r.get('case'),r.get('stage'),r.get('trace')) for r in runs]!=[(c,True,t) for c in ('nominal153','code153') for t in (False,True,True,False)] or len({r['id'] for r in runs})!=8 or len({r['command'][4] for r in runs})!=8:raise ValueError('exact learned observer population')
    else:
        if len(runs)!=3 or not runs[0].get('model_free') or [(r.get('case'),r.get('stage'),r.get('trace'),r.get('witness')) for r in runs[1:]]!=[(c,True,True,True) for c in ('nominal153','code153')]:raise ValueError('exact fixture and selected cases')
        runs=runs[1:]
    for r in runs:
        c=r['case'];fixture=json.loads(Path(r['command'][2]).read_text())[c];v,out=arm(r['command'][4],fixture,c,r['stage'],r['trace'],r.get('witness',False),p['expected_full_logits_sha256'][c],weights)
        v['stage_stats']=out['stage_stats'];cases.setdefault(c,[]).append(v);hashes.setdefault(c,[]).append(out['full33_logits_sha256'])
    result=evaluate(cases) if kind=='product' else observer(cases) if kind=='observer' else {'status':'PASS_SELECTED_LEARNED_R0_STAGING_FIDELITY','cases':{c:len(v) for c,v in cases.items()},'scope':'Original full33 reference and selected bytes; diagnostic timing is not promotion.'}
    result['full33_logits_sha256']=hashes;result['auxiliary_root']=str(weights);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--case');p.add_argument('--on',choices=('0','1'));p.add_argument('--trace',choices=('0','1'));p.add_argument('--witness',action='store_true');p.add_argument('--expected');p.add_argument('--weights',type=Path);p.add_argument('--family',choices=('diagnostic','observer','product'));p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    v=family(a.root,a.family) if a.family else arm(a.root,json.loads(a.fixture.read_text())[a.case],a.case,a.on=='1',a.trace=='1',a.witness,a.expected,a.weights)[1]
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
