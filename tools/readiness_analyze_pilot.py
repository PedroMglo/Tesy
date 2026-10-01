"""Apply the frozen signed net-benefit contract; no production timing claim."""
import json,math,statistics
from pathlib import Path

def analyze(rows,traces):
    names=['all-hit','mixed','all-absent'];pairs=[(0,1),(3,2),(4,5),(7,6)]
    if len(rows)!=24:raise ValueError('pilot must contain all 24 planned repetitions')
    summary=[]
    for name in names:
        selected=[r for r in rows if r['case']==name]
        if len(selected)!=8 or [r['rep'] for r in selected]!=list(range(8)) or [r['arm'] for r in selected]!=list('ABBAABBA'):
            raise ValueError('incomplete or reordered case')
        for r in selected:
            if not r['bitwise'] or not r['finite'] or not r['original_native_loader_direct'] or not math.isfinite(r['wall_s']) or r['wall_s']<=0 or r['native_hook_calls']!=96:
                raise ValueError('arithmetic/byte/plan/clock evidence missing')
            if r['arm']=='B' and r['consume_checks']!=96:raise ValueError('consumer hook not exercised')
        gains=[100*(selected[a]['wall_s']-selected[b]['wall_s'])/selected[a]['wall_s'] for a,b in pairs]
        savings=[1e6*(selected[a]['wall_s']-selected[b]['wall_s']) for a,b in pairs]
        summary.append({'case':name,'layer':selected[0]['layer'],'repetitions':selected,'pairs':pairs,
            'paired_gains_percent':gains,'median_paired_gain_percent':statistics.median(gains),
            'paired_signed_savings_us':savings,'median_signed_saving_us':statistics.median(savings)})
    savings={r['case']:r['median_signed_saving_us'] for r in summary};projections=[]
    for trace in traces:
        counts={n:0 for n in names};credit=0
        for row in trace['rows']:
            if row['tier']!='CPU':continue
            name='all-hit' if row['misses']==0 else 'all-absent' if row['misses']==4 else 'mixed'
            counts[name]+=1;saving=savings[name]
            credit+=min(saving,row['service_window_us'],row['following_router_gap_us'],1025.490) if saving>0 else saving
        projections.append({'run':trace['run'],'scope':trace['scope'],'decode_s':trace['decode_s'],
            'cpu_case_counts':counts,'signed_net_scenario_s':credit/1e6,
            'signed_net_full_decode_scenario_percent':100*credit/1e6/trace['decode_s']})
    hit=summary[0]
    median_hit=hit['median_paired_gain_percent']>=-5
    # Publish individual regressions as well; the owner's broad all-hit protection
    # is not claimed satisfied merely by a favorable noisy median.
    every_hit=all(g>=-5 for g in hit['paired_gains_percent'])
    opportunity=any(p['signed_net_full_decode_scenario_percent']>=5 for p in projections)
    return {'status':'GO_MINIMAL_READINESS_INTEGRATION_DESIGN' if median_hit and every_hit and opportunity else 'NO_GO_MINIMAL_READINESS_OVERLAP_IN_TESTED_SCOPE',
        'arithmetic_selected_scope':'PASS_BITWISE_FINITE_C127_AND_DIRECT_WITNESS','cases':summary,'conditional_projections':projections,
        'median_all_hit_guard_pass':median_hit,'all_individual_all_hit_regressions_within_5_percent':every_hit,
        'net_opportunity_5_percent_pass':opportunity,
        'reason':'No >=5% signed net opportunity under the frozen case transfer; all-hit individual timing also unstable.' if not opportunity else 'See separate all-hit protection.',
        'full_FFN_status':'FULL_FFN_RESTRUCTURE_ONLY_REMAINS_HYPOTHESIS',
        'limitations':['Conditional transfer of isolated miss masks/C127 activations to slots44 C-API traces, not exact replay.','Retained selected device caches and 4 repeated experts per case; no universal cold-IO conclusion.','All-hit positive timing differences receive no readiness overlap credit; signed regressions retained.','Observed load/compute concurrency may alter IO service and scheduling; no certified causal decomposition.','No confidence interval or complete 120B/server speedup from four pairs.','No individual samples removed; favorable all-hit median does not eliminate its -45.88% pair.'],
        'first_projection_source':'gate_MMID; native ascending physical slots; up and down graph boundaries unchanged',
        'production_speedup':'NOT_RUN','full_model_inference_s':0}

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];p=root/'results/c234-readiness-pilot-or-bound-20261001'
    rows=[json.loads(x) for x in (p/'raw/c234-pilot.stdout').read_text().splitlines()]
    receipt=json.loads((p/'raw/c234-pilot.json').read_text())
    if receipt['returncode']!=0 or receipt['stop_reason'] is not None or receipt['mapped_libraries_match_ldd'] is not True:raise ValueError('bounded receipt invalid')
    traces=json.loads((root/'results/c232-post-c231-readiness-20261001T180602Z/readiness-existing.json').read_text())['cases']
    result=analyze(rows,traces)
    result['measurement_commit']=json.loads((p/'family-receipt.json').read_text())['measurement_commit']
    result['resources']={k:receipt[k] for k in ('maxima','cgroup_end','cgroup_limit_enforced','relevant_environment','mapped_backend_libraries_sha256')}
    with (p/'pilot-analysis.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'net_percent':[r['signed_net_full_decode_scenario_percent'] for r in result['conditional_projections']],'all_hit_guard':result['all_individual_all_hit_regressions_within_5_percent']}))
