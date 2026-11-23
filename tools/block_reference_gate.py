"""Require every prospectively selected same-device reference; no missing rows."""
import argparse
import json
from pathlib import Path

from c94_session_wave_8k_reference import tree_digest


def analyze(root):
    root=Path(root).resolve();p=json.loads((root/'protocol.json').read_text());rows=[]
    for name, expected in p['capture_trees'].items():
        if tree_digest(Path(name))!=expected:raise ValueError('immutable capture changed')
    for run in p['runs']:
        text=(root/'raw'/(run['id']+'.stdout')).read_text().splitlines()
        out=[json.loads(line) for line in text if line.startswith('{')]
        if len(out)!=1:raise ValueError('reference missing/duplicate outcome')
        x=out[0]
        if x['tokens']!=run['B'] or not all(x[key] for key in ('routing_ids_equal','routing_weights_bitwise','ffn_bitwise')) or any(x[key] for key in ('routing_weights_nonfinite','ffn_nonfinite')):
            raise ValueError('reference numeric/finite/shape failure')
        rows.append(dict(id=run['id'],B=run['B'],layer=run['layer'],device=run['device'],reference=x))
    out=dict(status='PASS_SELECTED_BLOCK_CANONICAL_FFN',rows=rows,
             scope='New B2/4/8 block_base FFNs at layers0/25/35, native logical pool128, same devices and original slices; not all attention/KV or universal causal correctness')
    with (root/'reference-summary.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(out))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);analyze(p.parse_args().root)
