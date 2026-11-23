"""Strict auxiliary weight receipt; does not grant target correctness or speed."""
import argparse, hashlib, json, math, struct
from pathlib import Path

def inspect(root):
    root=Path(root);m=json.loads((root/'manifest.json').read_text())
    if m.get('schema')!='original-score-affine-calibration-v1' or m.get('status')!='PASS_FIXED_TRAINING_ONLY_FIT':raise ValueError('fit identity')
    if m.get('model_sha256')!='582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d' or m.get('CPU_target_layers')!=[2,24] or m.get('source_horizon')!=2:raise ValueError('original movement-only target linkage')
    if m.get('development_used') is not False or m.get('holdout_used') is not False or m.get('training_BLAS_actual_threads')!=8:raise ValueError('training-only/native BLAS contract')
    rows=m.get('training_conversations')
    if type(rows) is not list or len(rows)!=8 or len({r['case'] for r in rows})!=8 or any(type(r['frames']) is not int or not 16<=r['frames']<=128 for r in rows):raise ValueError('fixed eight actual training conversations')
    if not 512<=sum(r['frames'] for r in rows)<=1024 or m.get('training_rows_per_layer')!=sum(r['frames'] for r in rows):raise ValueError('training row gate')
    for f,n in (('weight.f32',23*128*128),('bias.f32',23*128)):
        data=(root/f).read_bytes()
        if len(data)!=n*4 or hashlib.sha256(data).hexdigest()!=m['sha256'][f] or any(not math.isfinite(v[0]) for v in struct.iter_unpack('<f',data)):raise ValueError('bounded finite weights/hash')
    if m.get('weights_bytes')!=1519104 or not math.isfinite(m.get('fit_s',float('nan'))) or m['fit_s']<=0:raise ValueError('parameter/cost receipt')
    return {'status':'PASS_FIXED_TRAINING_ONLY_FIT_RECEIPT','training_rows_per_layer':m['training_rows_per_layer'],'weights_bytes':m['weights_bytes'],'fit_s':m['fit_s'],'classification':'MEDIDO_NO_TARGET','scope':'Auxiliary fit only. Target unchanged; native evaluation and service/utility gates remain.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=inspect(a.root)
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
