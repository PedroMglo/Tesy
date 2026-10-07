"""Fixed task-disjoint affine fit. This never reads development/holdout labels."""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from expert_prediction_corpus_gate import inspect
from expert_score_calibration import fit

def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def train(protocol, output):
    output=Path(output)
    if output.exists(): raise ValueError('new training output required')
    fixture=json.loads(Path(protocol['official_fixture']).read_text())
    tasks=json.loads(Path(protocol['tasks']).read_text())
    runs=protocol['runs']
    if len(runs)!=8 or [r['case'] for r in runs]!=[t['id'] for t in tasks] or len(set(r['root'] for r in runs))!=8:
        raise ValueError('exact eight ordered independent training conversations')
    arrays=[];receipts=[];total=0
    for r in runs:
        root=Path(r['root']);v=inspect(root,fixture[r['case']],r['case'])
        n=v['decode_calls']
        if n<16: raise ValueError('training conversation has fewer than frozen 16 frames')
        total+=n
        arrays.append(tuple(np.fromfile(root/f,dtype='<f4').reshape(n,23,128)
                            for f in ('early-native-scores.f32','true-routing-scores.f32')))
        receipts.append({'case':r['case'],'frames':n,'root':str(root),
                         'sha256':{f:checksum(root/f) for f in
                                   ('result.json','early-native-scores.f32','true-routing-scores.f32','actual-router-ids.json')}})
    if not 512<=total<=1024:raise ValueError('frozen total training row gate')
    x=np.concatenate([a[0] for a in arrays]);y=np.concatenate([a[1] for a in arrays])
    begin=time.monotonic();weights=[];bias=[]
    for layer in range(23):
        w,b=fit(x[:,layer,:],y[:,layer,:])
        if not np.isfinite(w).all() or not np.isfinite(b).all():raise ValueError('nonfinite F32 auxiliary weights')
        weights.append(w);bias.append(b)
    elapsed=time.monotonic()-begin
    w=np.stack(weights);b=np.stack(bias)
    if w.nbytes+b.nbytes!=1519104:raise ValueError('frozen parameter bound')
    output.mkdir()
    w.tofile(output/'weight.f32');b.tofile(output/'bias.f32')
    result={'schema':'original-score-affine-calibration-v1','status':'PASS_FIXED_TRAINING_ONLY_FIT',
            'classification':'MEDIDO_NO_TARGET','source_horizon':2,'CPU_target_layers':[2,24],
            'feature_dimension':128,'output_dimension':128,'training_rows_per_layer':total,
            'training_conversations':receipts,'fit_s':elapsed,'fit':'identity-prior standardized ridge lambda=n, F64 solve/F32 stored',
            'weights_layout':'23 layers, W[output,input] row-major little-endian F32; GGML ne0=input, ne1=output',
            'weights_bytes':w.nbytes+b.nbytes,'sha256':{'weight.f32':checksum(output/'weight.f32'),'bias.f32':checksum(output/'bias.f32')},
            'numpy_version':np.__version__,'development_used':False,'holdout_used':False,
            'scope':'Auxiliary movement-only weights; no target fine-tuning, router replacement, latency or quality claim.'}
    (output/'manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('protocol',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    print(train(json.loads(a.protocol.read_text()),a.output)['status'])
if __name__=='__main__':main()
