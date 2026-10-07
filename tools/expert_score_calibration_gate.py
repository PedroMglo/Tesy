"""Native movement-only affine, with independent F64 value reference."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np

def native(root,weights,source):
    root=Path(root);weights=Path(weights);source=Path(source)
    m=json.loads((weights/'manifest.json').read_text());v=json.loads((root/'result.json').read_text())
    if m.get('schema')!='original-score-affine-calibration-v1' or m.get('training_rows_per_layer',0)<512 or m.get('development_used') is not False or m.get('holdout_used') is not False or m.get('weights_bytes')!=1519104:
        raise ValueError('fixed training-only auxiliary identity')
    for f in ('weight.f32','bias.f32'):
        if hashlib.sha256((weights/f).read_bytes()).hexdigest()!=m['sha256'][f]:raise ValueError('auxiliary weights hash')
    if v.get('schema')!='native-score-affine-evaluation-v1' or v.get('status')!='PASS_NATIVE_AFFINE_EVALUATION' or v.get('threads')!=8 or v.get('layers')!=[2,24] or v.get('repetitions')!=4 or v.get('all_repeats_bitwise') is not True:
        raise ValueError('actual native affine contract')
    n=v.get('frames')
    if type(n) is not int or not 16<=n<=128:raise ValueError('actual native input frame bound')
    p=source/'prediction-scores.f32'
    if not p.exists():p=source/'early-native-scores.f32'
    if v.get('input')!=str(p):raise ValueError('source score path')
    def array(p,shape):
        if p.stat().st_size!=math.prod(shape)*4:raise ValueError('native array exact size')
        a=np.fromfile(p,dtype='<f4').reshape(shape)
        if not np.isfinite(a).all():raise ValueError('nonfinite native scores')
        return a
    x=array(p,(n,23,128));w=array(weights/'weight.f32',(23,128,128));b=array(weights/'bias.f32',(23,128));y=array(root/'corrected-scores.f32',(n,23,128))
    # Frozen standard dot-product forward-error envelope. This is an auxiliary
    # F32 operator check, not a tolerance for changing target arithmetic.
    eps=float(np.finfo(np.float32).eps);gamma=257*eps/(1-257*eps)
    maximum=0.
    for l in range(23):
        xf=x[:,l].astype(np.float64);wf=w[l].astype(np.float64);bf=b[l].astype(np.float64)
        reference=xf@wf.T+bf;bound=gamma*(np.abs(xf)@np.abs(wf).T+np.abs(bf)+1.)
        error=np.abs(y[:,l].astype(np.float64)-reference)
        if (error>bound).any():raise ValueError('independent native affine value reference')
        maximum=max(maximum,float(error.max()))
    top=np.argsort(-y,kind='stable',axis=2)[:,:,:4].ravel().tolist()
    if v.get('top4_ids')!=top:raise ValueError('actual native affine top4 mapping')
    dt=v.get('score_cost_median_us')
    if type(dt) is not list or len(dt)!=n*23 or any(type(t) not in (int,float) or not math.isfinite(t) or t<=0 for t in dt):raise ValueError('measured finite complete native affine costs')
    return {'status':'PASS_NATIVE_AFFINE_REFERENCE','frames':n,'maximum_absolute_error':maximum,
            'gamma257':gamma,'calibration_complete_s':sum(dt)/1e6,'cost_us':dt,'native_top4':top,
            'classification':'MEDIDO_NO_TARGET','scope':'Isolated CPU8 auxiliary F32 operator includes input/compute/sync/output/sort. No full target or contention and no measured useful gain.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('weights',type=Path);p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=native(a.root,a.weights,a.source)
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
