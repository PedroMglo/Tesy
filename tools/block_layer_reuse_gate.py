"""New R2 fidelity boundary; historical validators and results stay intact."""
import argparse
import json
from pathlib import Path
import numpy as np
from c210_witness_gate import qualified
from run_bounded import sha256

STAGES=('attn_post_norm','ffn_moe_logits','ffn_moe_logits_biased',
        'ffn_moe_topk','ffn_moe_weights_softmax','ffn_moe_out')
SELECTED=(0,12,24,25,35)


def components(rows, unions):
    if type(rows) is not list or not rows or len(rows)%6:
        raise ValueError('complete consumer components missing')
    covered={layer:set() for layer in SELECTED}
    for start in range(0,len(rows),6):
        group=rows[start:start+6]
        base={k:group[0].get(k) for k in ('layer','wave','logical','slot','generation')}
        if any(type(v) is not int for v in base.values()) or base['layer'] not in SELECTED or \
           not -1<=base['wave']<8 or not 0<=base['logical']<128 or \
           not 0<=base['slot']<40 or base['generation']<=0:
            raise ValueError('consumer identity/generation invalid')
        for component,row in enumerate(group):
            if {k:row.get(k) for k in base}!=base or row.get('component')!=component or \
               row.get('bytes')!=(4406400 if component<3 else 11520):
                raise ValueError('wrong or missing bias/weight slice component')
        covered[base['layer']].add(base['logical'])
    if covered!=unions:raise ValueError('consumer witness and authoritative routes differ')
    return len(rows)


def inspect(directory,fixture,mode):
    directory=Path(directory);v=json.loads((directory/'result.json').read_text())
    if v.get('status')!='COMPLETE_NATIVE_LAYER_REUSE_FIDELITY' or v.get('mode')!=mode or \
       v.get('input_ids')!=fixture['ids'] or v.get('teacher_forced_ids')!=fixture['continuation_ids'][:6] or \
       v.get('layer_span')!=153 or v.get('ffn_tile')!=32:
        raise ValueError('native input/profile/position contract changed')
    winners=v.get('native_argmax_ids')
    if type(winners) is not list or len(winners)!=7 or any(type(x) is not int or not 0<=x<201088 for x in winners):
        raise ValueError('native argmax/output rows missing')
    for state_name in ('initial','after_prefill'):
        s=v.get(state_name,{})
        if s.get('pending_queue')!=0 or [x.get('layer') for x in s.get('layers',[])]!=list(range(36)):
            raise ValueError('complete drained expert state missing')
        for layer in s['layers']:
            if len(layer.get('slot_generation',[]))!=40 or len(layer.get('slot_state',[]))!=40 or len(layer.get('slot_claimed',[]))!=40 or len(layer.get('slot_expert',[]))!=40 or \
               any(layer.get('slot_claimed',[True])) or any(x not in (0,2) for x in layer['slot_state']):
                raise ValueError('claimed/loading/missing native slots')
    stages=v.get('stages');expected={(l,s) for l in range(36) for s in STAGES}
    if type(stages) is not list or len(stages)!=len(expected) or \
       {(r.get('layer'),r.get('stage')) for r in stages}!=expected:
        raise ValueError('whole layer stages omitted/duplicated')
    payloads={};unions={};total=0
    for r in stages:
        layer,stage=r['layer'],r['stage'];n=1 if layer==35 else 153
        shape=[2880,n,1,1] if stage in ('attn_post_norm','ffn_moe_out') else \
              [4,n,1,1] if stage=='ffn_moe_topk' else \
              [1,4,n,1] if stage=='ffn_moe_weights_softmax' else [128,n,1,1]
        dtype='i32' if stage=='ffn_moe_topk' else 'f32'
        native=f'ffn_moe_probs-{layer}' if stage=='ffn_moe_logits_biased' else f'{stage}-{layer}'
        if r.get('ne')!=shape or r.get('dtype')!=dtype or r.get('name')!=f'{stage}-{layer}' or r.get('file')!=f'{stage}-{layer}.bin' or r.get('native_name')!=native:
            raise ValueError('native whole-layer shape/type changed')
        path=directory/r['file'];size=int(np.prod(shape))*4
        if not path.is_file() or path.stat().st_size!=size or r.get('bytes')!=size:
            raise ValueError('missing/truncated native payload')
        a=np.fromfile(path,dtype='<i4' if dtype=='i32' else '<f4')
        if dtype=='f32' and not np.isfinite(a).all():raise ValueError('nonfinite stage')
        if stage=='ffn_moe_topk':
            if ((a<0)|(a>=128)).any() or any(len(set(row))!=4 for row in a.reshape(-1,4)):
                raise ValueError('invalid/duplicate routed experts')
            if layer in SELECTED:unions[layer]=set(map(int,a))
        payloads[f'{layer}:{stage}']=sha256(path);total+=size
    if total!=v.get('capture_bytes') or total>256*2**20:raise ValueError('capture accounting/bound wrong')
    count=components(v.get('witness'),unions)
    for name in ['prefill.logits.f32',*[f'decode{i}.logits.f32' for i in range(6)]]:
        p=directory/name
        if not p.is_file() or p.stat().st_size!=201088*4 or not np.isfinite(np.fromfile(p,dtype='<f4')).all():
            raise ValueError('complete finite native logit row missing')
        payloads[name]=sha256(p)
    return {'status':'PASS_NATIVE_R2_COMPLETE_LAYER_CAPTURE','mode':mode,'stage_payloads':payloads,
            'consumer_components':count,'initial':v['initial'],'native_argmax_ids':winners,
            'scope':'Bounded warm153 R2 and six teacher-forced decode calls; not useful latency or universal8K'}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--fixture',type=Path)
    p.add_argument('--mode');p.add_argument('--paired-root',type=Path);p.add_argument('--bridge-reference',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.bridge_reference:
        old,new=qualified(a.bridge_reference),qualified(a.directory)
        for key in ('core','masks','logits'):
            if old[key]!=new[key]:raise ValueError('unchanged R0 bridge differs')
        out={'status':'PASS_PRIVATE_R0_SELECTED_BRIDGE','core_payloads':len(new['core']),
             'full_logits':len(new['logits']),'prospective_witness':new['prospective_witness']}
    else:
        fixture=json.loads(a.fixture.read_text())['anchor-nominal153'];out=inspect(a.directory,fixture,a.mode)
        if a.paired_root:
            other=inspect(a.paired_root,fixture,'r2-tile')
            if {k:out['initial'][k] for k in ('layers','pending_queue','n_calls')}!= \
               {k:other['initial'][k] for k in ('layers','pending_queue','n_calls')}:
                raise ValueError('paired complete initial expert state differs')
            if out['stage_payloads']!=other['stage_payloads']:raise ValueError('same-profile R2 payload/logit fidelity differs')
            out['status']='PASS_R2_TILE_SHARED_FIDELITY'
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])

if __name__=='__main__':main()
