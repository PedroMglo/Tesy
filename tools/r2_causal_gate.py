"""Prospective R0/T/E input-work ablation; historical gates remain intact."""
import argparse
import json
import math
from pathlib import Path
import statistics

import numpy as np
from block_prefill_timing_gate import loads
from run_bounded import sha256

MODES={'R0':0,'T':1,'E':2}
METRICS=('prefix_s','prefill153_s','decode32_s','total_s')


def validate(v,fixture,profile,case):
    ids=fixture['ids']; n=len(ids); prefix=n-153
    plan=[min(256,prefix-p) for p in range(0,prefix,256)]+[153]
    if profile not in MODES or n not in (2197,2105) or len(fixture['continuation_ids'])!=32:
        raise ValueError('frozen development fixture invalid')
    expected={'status':'COMPLETE_NATIVE_R2_CAUSAL_WORK','profile':profile,'case':case,
              'official_input_ids':ids,'teacher_forced_ids':fixture['continuation_ids'],
              'external_prefill_calls':plan,'decode_calls':32,'decode_positions':[n,n+31],
              'output_rows':33,'vocab':201088,'FFN_last_layer_rows_per_call':1,
              'mode':MODES[profile],'layerspan':32 if profile=='R0' else 153,
              'numerical_FFN_tiles':[32,32,32,32,25],
              'last_use_order_env':None if profile=='R0' else '1',
              'initial_prefix_mode':0,'full_row_retention_bytes':33*201088*4}
    if any(v.get(k)!=value for k,value in expected.items()):
        raise ValueError('input/profile/mode/shape/call accounting mismatch')
    for name in ('official_input_ids','teacher_forced_ids','native_argmax_ids'):
        a=v.get(name)
        expected_n=n if name=='official_input_ids' else 32 if name=='teacher_forced_ids' else 33
        if type(a) is not list or len(a)!=expected_n or any(type(x) is not int or not 0<=x<201088 for x in a):
            raise ValueError('native IDs invalid or absent')
    for k in METRICS:
        x=v.get(k)
        if type(x) not in (int,float) or not math.isfinite(x) or x<=0:
            raise ValueError('invalid finite observed metric '+k)
    if not math.isclose(v['total_s'],v['prefill153_s']+v['decode32_s'],rel_tol=1e-10,abs_tol=1e-8):
        raise ValueError('phase clocks inconsistent')
    for key in ('initial','final'):
        state=v.get(key,{})
        if state.get('pending_queue')!=0 or [x.get('layer') for x in state.get('layers',[])]!=list(range(36)):
            raise ValueError('complete drained state absent')
        for l in state['layers']:
            if any(type(l.get(k)) is not list or len(l[k])!=40 for k in ('slot_expert','slot_state','slot_generation','slot_claimed')) or any(l['slot_claimed']) or any(x not in (0,2) for x in l['slot_state']):
                raise ValueError('initial/final slot state invalid')
    loads(v)
    return v


def validate_runs(runs, numeric=False):
    expected=[('code153',p) for p in ('T','E')] if numeric else [(c,p) for c in ('nominal153','code153') for p in ('R0','T','E','E','T','R0')]
    if len(runs)!=len(expected):raise ValueError('exact frozen run cardinality required')
    ids=[r['id'] for r in runs]; paths=[str(Path(r['command'][4]).resolve()) for r in runs]
    if len(set(ids))!=len(ids) or len(set(paths))!=len(paths):raise ValueError('run identity/output root reused')
    if [(r['command'][3],r['profile']) for r in runs]!=expected:raise ValueError('frozen case/profile order differs')
    for r in runs:
        if len(r['command'])!=7 or r['command'][5]!=r['profile'] or r['command'][6]!='v1':raise ValueError('native command contract differs')


def inspect(directory,fixture,profile,case):
    directory=Path(directory);v=validate(json.loads((directory/'result.json').read_text()),fixture,profile,case)
    p=directory/'all33.logits.f32'
    if not p.is_file() or p.stat().st_size!=33*201088*4:
        raise ValueError('full native rows missing/truncated')
    rows=np.fromfile(p,dtype='<f4').reshape(33,201088)
    if not np.isfinite(rows).all() or rows.argmax(axis=1).tolist()!=v['native_argmax_ids']:
        raise ValueError('full finite row/argmax evidence invalid')
    return v,sha256(p)


def initial_identity(v):
    return {k:v['initial'][k] for k in ('layers','pending_queue','n_calls')}


def contrast(rows,left,right):
    pairs=[]
    for block in ((0,1,2),(5,4,3)):
        index={'R0':block[0],'T':block[1],'E':block[2]};a,b=rows[index[left]],rows[index[right]]
        if initial_identity(a)!=initial_identity(b):raise ValueError('initial expert state differs')
        pairs.append({'reference_arm':index[left]+1,'candidate_arm':index[right]+1,
                      'gain_percent':{k:100*(a[k]-b[k])/a[k] for k in METRICS},
                      'loads_reference':loads(a),'loads_candidate':loads(b),
                      'native_argmax_equal':a['native_argmax_ids']==b['native_argmax_ids']})
    med={k:statistics.median(p['gain_percent'][k] for p in pairs) for k in METRICS}
    return {'pairs':pairs,'median_paired_gain_percent':med}


def evaluate(cases):
    if set(cases)!={'nominal153','code153'}:raise ValueError('both frozen cases required')
    reports={}
    for case,rows in cases.items():
        if len(rows)!=6 or [x['profile'] for x in rows]!=['R0','T','E','E','T','R0']:
            raise ValueError('exact six-arm order/cardinality required')
        if any(x['case']!=case for x in rows):raise ValueError('case labels mixed')
        # Compare all three references in each frozen block, never choose neighbors.
        reports[case]={f'{a}_vs_{b}':contrast(rows,a,b) for a,b in (('R0','T'),('R0','E'),('T','E'))}
    def eligible(p):
        return all(r['median_paired_gain_percent']['prefill153_s']>=8 and
                   all(x['gain_percent']['prefill153_s']>0 for x in r['pairs']) and
                   r['median_paired_gain_percent']['total_s']>0 and
                   all(r['median_paired_gain_percent'][k]>=-5 for k in ('decode32_s','prefix_s'))
                   for r in (reports[c]['R0_vs_'+p] for c in reports))
    ok={p:eligible(p) for p in ('T','E')}
    extra=all(r['median_paired_gain_percent']['total_s']>=3 and
              all(x['gain_percent']['total_s']>0 for x in r['pairs']) and
              r['median_paired_gain_percent']['decode32_s']>=-5
              for r in (reports[c]['T_vs_E'] for c in reports))
    winner='E' if ok['E'] and (not ok['T'] or extra) else 'T' if ok['T'] else None
    return {'status':'GO_CAUSAL_COST_'+winner if winner else 'NO_GO_R2_CAUSAL_COST',
            'selected':winner,'eligible_vs_R0':ok,'E_coordination_cost_gate_pass':extra,'cases':reports,
            'scope':'Same supplied native inputs and calls; T/E same numerical profile; R0 cross-profile. No natural/committed throughput or physical traffic claim.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--fixture',type=Path)
    p.add_argument('--profile',choices=MODES);p.add_argument('--case');p.add_argument('--family',action='store_true')
    p.add_argument('--numeric',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.family or a.numeric:
        protocol=json.loads((a.directory/'protocol.json').read_text());cases={};hashes={}
        validate_runs(protocol['runs'],a.numeric)
        for run in protocol['runs']:
            cmd=run['command'];case=cmd[3];fixture=json.loads(Path(cmd[2]).read_text())[case]
            v,h=inspect(cmd[4],fixture,run['profile'],case);cases.setdefault(case,[]).append(v);hashes.setdefault(case,[]).append(h)
        if a.numeric:
            if set(cases)!={'code153'} or [x['profile'] for x in cases['code153']]!=['T','E']:
                raise ValueError('additional numeric pair contract')
            x,y=cases['code153']
            if initial_identity(x)!=initial_identity(y) or hashes['code153'][0]!=hashes['code153'][1]:
                raise ValueError('FAIL_SAME_PROFILE_T_E_FULL_ROWS')
            out={'status':'PASS_SELECTED_NEW_INPUT_T_E_FULL33_LOGITS','case':'code153','full_logits_sha256':hashes['code153'][0],'native_IDs_equal':True}
        else:
            # Equality is mandatory for T/E on each paired case, not R0/R2.
            for case,h in hashes.items():
                if len(h)!=6 or h[1]!=h[2] or h[4]!=h[3]:raise ValueError('same-profile full rows differ')
            out=evaluate(cases)
    else:
        fixture=json.loads(a.fixture.read_text())[a.case];v,h=inspect(a.directory,fixture,a.profile,a.case)
        out={'status':'PASS_CAUSAL_NATIVE_ARM','profile':a.profile,'case':a.case,
             'metrics':{k:v[k] for k in METRICS},'loads':loads(v),'full_logits_sha256':h}
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])


if __name__=='__main__':main()
