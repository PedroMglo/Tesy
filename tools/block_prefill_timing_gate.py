"""Controlled native input-cost screen; no natural utility/throughput claim."""
import argparse
import json
import math
import statistics
from pathlib import Path
import numpy as np
from run_bounded import sha256

METRICS=('prefix2044_s','prefill153_s','decode32_s','total_s')


def validate(v,fixture,profile):
    if v.get('status')!='COMPLETE_CONTROLLED_WARM153_NATIVE_SERVICE' or v.get('profile')!=profile or v.get('official_input_ids')!=fixture['ids'] or v.get('teacher_forced_ids')!=fixture['continuation_ids'][:32] or v.get('external_prefill_calls')!=[256]*7+[252,153] or v.get('decode_calls')!=32 or v.get('decode_positions')!=[2197,2228] or v.get('output_rows')!=33 or v.get('FFN_last_layer_rows_per_call')!=1 or v.get('layerspan')!=(32 if profile=='A' else 153) or v.get('numerical_FFN_tiles')!=[32,32,32,32,25]:
        raise ValueError('controlled official input/profile/call contract incomplete')
    ids=v.get('native_argmax_ids')
    if type(ids) is not list or len(ids)!=33 or any(type(x) is not int or not 0<=x<201088 for x in ids):raise ValueError('native output row accounting missing')
    for k in METRICS:
        x=v.get(k)
        if type(x) not in (int,float) or not math.isfinite(x) or x<=0:raise ValueError('invalid observed metric '+k)
    if not math.isclose(v['total_s'],v['prefill153_s']+v['decode32_s'],rel_tol=1e-10,abs_tol=1e-8):raise ValueError('overlapping/inconsistent phase clocks')
    for name in ('initial','final'):
        state=v.get(name,{})
        if state.get('pending_queue')!=0 or [l.get('layer') for l in state.get('layers',[])]!=list(range(36)):raise ValueError('complete drained state missing')
        for layer in state['layers']:
            if any(len(layer.get(k,[]))!=40 for k in ('slot_expert','slot_state','slot_generation','slot_claimed')) or any(layer['slot_claimed']) or any(x not in (0,2) for x in layer['slot_state']):raise ValueError('incomplete/resident state invalid')
    return v


def loads(v):
    result={'CPU':0,'GPU':0}
    for a,b in zip(v['initial']['layers'],v['final']['layers']):
        delta=[y-x for x,y in zip(a['slot_generation'],b['slot_generation'])]
        if any(type(x) is not int or x<0 for x in delta):raise ValueError('generation regressed/noninteger')
        result['CPU' if a['layer']<25 else 'GPU']+=sum(delta)
    return result


def paired(arms):
    if len(arms)!=4 or [x['profile'] for x in arms]!=['A','B','B','A']:raise ValueError('exact four-arm ABBA cardinality required')
    pairs=[]
    for ai,bi in ((0,1),(3,2)):
        a,b=arms[ai],arms[bi]
        if {k:a['initial'][k] for k in ('layers','pending_queue','n_calls')}!={k:b['initial'][k] for k in ('layers','pending_queue','n_calls')}:raise ValueError('complete initial expert state differs')
        la,lb=loads(a),loads(b)
        pairs.append({'A_arm':ai+1,'B_arm':bi+1,'gain_percent':{k:100*(a[k]-b[k])/a[k] for k in METRICS},'loads_A':la,'loads_B':lb,'greedy_rows_equal':a['native_argmax_ids']==b['native_argmax_ids']})
    medians={k:statistics.median(x['gain_percent'][k] for x in pairs) for k in METRICS}
    passed=medians['prefill153_s']>=8 and all(x['gain_percent']['prefill153_s']>0 for x in pairs) and medians['decode32_s']>=-5 and medians['prefix2044_s']>=-5 and all(sum(x['loads_B'].values())<sum(x['loads_A'].values()) for x in pairs)
    return dict(status='GO_CONTROLLED_WARM153_NATIVE_COST' if passed else 'NO_GO_CONTROLLED_WARM153_NATIVE_COST',pairs=pairs,median_paired_gain_percent=medians,scope='Fixed official warm153 input plus32teacher-forced calls; cross-profile computation may differ, no generated/confirmed throughput or natural utility claim')


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--profile');p.add_argument('--family',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.family:
        protocol=json.loads((a.directory/'protocol.json').read_text());arms=[]
        for run in protocol['runs']:
            fixture=json.loads(Path(run['command'][2]).read_text())['anchor-nominal153']
            arms.append(validate(json.loads((Path(run['command'][4])/'result.json').read_text()),fixture,run['profile']))
        out=paired(arms)
    else:
        fixture=json.loads(a.fixture.read_text())['anchor-nominal153'];v=validate(json.loads((a.directory/'result.json').read_text()),fixture,a.profile)
        checks={}
        for name in ('prefill.logits.f32','last-decode.logits.f32'):
            f=a.directory/name
            if not f.is_file() or f.stat().st_size!=201088*4 or not np.isfinite(np.fromfile(f,dtype='<f4')).all():raise ValueError('complete finite logit evidence missing')
            checks[name]=sha256(f)
        out=dict(status='PASS_CONTROLLED_NATIVE_ARM',profile=a.profile,metrics={k:v[k] for k in METRICS},loads=loads(v),logit_sha256=checks)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])

if __name__=='__main__':main()
