"""Deterministic all-expert lossless index from pinned GGUF metadata, no payload read."""
import argparse,json
from pathlib import Path
from run_bounded import sha256

def generate(metadata,sample,model_stat):
    if sha256(metadata)!=sample['metadata_sha256']:raise ValueError('GGUF metadata identity changed')
    rows=[json.loads(x) for x in Path(metadata).read_text().splitlines()]
    tensors={x['name']:x for x in rows[1:]}
    if len(tensors)!=len(rows)-1:raise ValueError('duplicate GGUF metadata')
    spec={k:v for k,v in sample.items() if k!='experts'}
    spec.update(schema='tesy-expert-local-integral-store-v1',store_scope='INTEGRAL_GPT_OSS120B_36x128',selection_rule='All36layers/all128experts; after C289 sample investment gate and live storage admission',model_stat=model_stat,experts=[])
    for layer in range(36):
        for expert in range(128):
            components=[]
            for kind in ['weight','bias']:
                for direction in ['gate','down','up']:
                    name=f'blk.{layer}.ffn_{direction}_exps.{kind}';t=tensors[name];size=4406400 if kind=='weight' else 11520
                    if t['shape']!=([2880,2880,128] if kind=='weight' else [2880,128]) or t['n_bytes']!=128*size or t['tensor_type']!=('mxfp4' if kind=='weight' else 'f32') or not 0<=t['data_offset']<=model_stat['size_bytes']-128*size:raise ValueError('GGUF component type/shape/range changed')
                    components.append({'name':name,'source_offset':t['data_offset']+size*expert,'size_bytes':size,'type':t['tensor_type']})
            spec['experts'].append({'layer':layer,'tier':'CPU' if layer<25 else 'GPU','expert':expert,'components':components})
    return spec
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('metadata',type=Path);a.add_argument('sample',type=Path);a.add_argument('protocol',type=Path);a.add_argument('output',type=Path);v=a.parse_args();result=generate(v.metadata,json.loads(v.sample.read_text()),json.loads(v.protocol.read_text())['model_stat'])
    with v.output.open('x')as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
