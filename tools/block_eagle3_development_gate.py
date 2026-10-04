"""Prospective native development discriminator; not a functional utility screen."""
import argparse
import json
import statistics
from pathlib import Path
from block_eagle3_loop_gate import validate, residency
from block_verifier_contract import paired_gain

CLASSES=('development-code-rle','development-structured-route')


def evaluate(arms):
    if type(arms) is not list or len(arms)!=8:raise ValueError('eight attempted arms required')
    for arm in arms:
        if type(arm) is not dict or type(arm.get('official_prefix_ids')) is not list or not arm['official_prefix_ids']:raise ValueError('official input IDs missing')
        validate(arm,{'ids':arm['official_prefix_ids']})
    out=[];all_go=True
    for n,case in enumerate(CLASSES):
        rows=arms[n*4:n*4+4]
        if [r.get('case') for r in rows]!=[case]*4 or [r.get('mode') for r in rows]!=['ar','head-measure','head-measure','ar'] or any(r.get('count_limit')!=32 for r in rows):raise ValueError('development class/order/shape changed')
        if any(r['official_prefix_ids']!=rows[0]['official_prefix_ids'] for r in rows):raise ValueError('paired prompts diverged')
        pairs=[]
        for ia,ib in ((0,1),(3,2)):
            a,b=rows[ia],rows[ib]
            same_count=a['decode_confirmed_excluding_anchor']==b['decode_confirmed_excluding_anchor']==32
            gain=paired_gain(a['wall_s'],b['wall_s']) if same_count else None
            prefill=paired_gain(a['prefill_total_s'],b['prefill_total_s'])
            pairs.append({'A_arm':ia+1,'B_arm':ib+1,'A_wall_s':a['wall_s'],'B_wall_s':b['wall_s'],
                'same_count_32':same_count,'gain_percent':gain,'prefill_gain_percent':prefill,
                'native_confirmed_ids_equal':a['native_confirmed_ids']==b['native_confirmed_ids'],
                'A_decode_count':a['decode_confirmed_excluding_anchor'],'B_decode_count':b['decode_confirmed_excluding_anchor'],
                'B_actual_matched_proposals':sum(r['accepted_draft_count'] for r in b['iterations']),
                'B_native_proposals_generated':sum(len(r['native_proposals']) for r in b['iterations']),
                'B_target_calls':b['target_verification_calls'],'B_full_logit_rows':b['target_full_logit_rows'],
                'B_mean_new_confirmed_per_verification':b['decode_confirmed_excluding_anchor']/b['target_verification_calls'],
                'B_draft_s':b['draft_total_s'],'B_feature_process_s':b['verification_head_processing_s']})
        gains=[p['gain_percent'] for p in pairs];median=statistics.median(gains) if None not in gains else None
        median_prefill=statistics.median(p['prefill_gain_percent'] for p in pairs)
        go=median is not None and median>=8 and all(g>0 for g in gains) and median_prefill>=-5
        all_go &= go
        out.append({'class':case,'pairs':pairs,'median_decode_gain_percent':median,'median_prefill_gain_percent':median_prefill,
                    'decision':'GO_DEVELOPMENT_INTEGRATED_DECODE' if go else ('INCONCLUSIVE_DEVELOPMENT_OUTPUT_COUNT' if median is None else 'NO_GO_DEVELOPMENT_INTEGRATED_DECODE')})
    return {'decision':'GO_DEVELOPMENT_REAL_UTILITY_SCREEN' if all_go else 'NO_GO_CURRENT_HEAD_GRID_DEVELOPMENT_SCREEN',
            'classes':out,'scope':'Two short native development classes; actual head proposals, fixed32 newly confirmed decode tokens and complete costs. This is not a 2K functional utility screen or M4.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();proto=json.loads((a.directory/'protocol.json').read_text());fixtures=json.loads(Path(proto['development_fixture']).read_text());arms=[]
    native_roots=[]
    for run in proto['runs']:
        native=Path(run['command'][5]);v=json.loads((native/'result.json').read_text());validate(v,fixtures[v['case']]);arms.append(v);native_roots.append(native)
    result=evaluate(arms)
    result['native_residency']=[residency(d,v) for d,v in zip(native_roots,arms)]
    for a,b in ((0,1),(3,2),(4,5),(7,6)):
        result['native_residency'][b]=residency(native_roots[b],arms[b],native_roots[a])
    with (a.directory/'development-screen.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['decision'])

if __name__=='__main__':main()
