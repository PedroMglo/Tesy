"""C233 per-origin conditional envelopes; no production speedup inference."""
import json,statistics,hashlib
from pathlib import Path
from readiness_feasibility import optimistic_overlap,ordered_gain

def envelope(case,work):
    rows=[r for r in case['rows'] if r['tier']=='CPU']
    wake=sum(r['wake_tail_us'] for r in rows)
    # The first op/full FFN must fit inside the observed following-router gap.
    # This still includes unshiftable attention/router work: an optimistic cap only.
    coarse=sum(min(r['service_window_us'],work,r['following_router_gap_us']) for r in rows)
    refined=sum(optimistic_overlap(r['release_us'],min(work,r['following_router_gap_us']),r['all_ready_us'],r['wait_begin_us']) for r in rows)
    ordered=sum(ordered_gain(r['release_us'],r['slots'],min(work,r['following_router_gap_us']),r['wait_begin_us'],r['wait_end_us']) for r in rows)
    scale=100/1e6/case['decode_s']
    return {'coarse_percent_including_separate_wake':(coarse+wake)*scale,
            'uniform_service_release_scenario_percent':(refined+wake)*scale,
            'ascending_slot_uniform_service_scenario_percent':ordered*scale,
            'wake_tail_s':wake/1e6,'service_credit_s':coarse/1e6}

if __name__=='__main__':
    repo=Path(__file__).resolve().parents[1];out=repo/'results/c233-readiness-native-operator-20261001'
    rows=[json.loads(line) for layer in (0,12,24) for line in (out/'raw'/f'c233-layer{layer}.stdout').read_text().splitlines()]
    assert len(rows)==288 and all(r['bitwise'] and r['finite'] for r in rows)
    stats=[]
    for layer in (0,12,24):
        for pool in (40,44):
            subset=[r for r in rows if r['layer']==layer and r['slots']==pool]
            stats.append({'layer':layer,'slots':pool,'n':len(subset),**{k:{'min':min(r[k] for r in subset),'median':statistics.median(r[k] for r in subset),'max':max(r[k] for r in subset)} for k in ('first_us','full_ffn_us')}})
    traces=json.loads((repo/'results/c232-post-c231-readiness-20261001T180602Z/readiness-existing.json').read_text())
    pool44=[r for r in rows if r['slots']==44]
    max_first=max(r['first_us'] for r in pool44);max_full=max(r['full_ffn_us'] for r in pool44)
    cases=[{'run':c['run'],'scope':c['scope'],'decode_s':c['decode_s'],
            'max_first_us':max_first,'max_full_us':max_full,
            'first_max_observed_scenario':envelope(c,max_first),
            'first_median_observed_scenario':envelope(c,statistics.median(r['first_us'] for r in pool44)),
            'full_max_observed_scenario':envelope(c,max_full),
            'full_median_observed_scenario':envelope(c,statistics.median(r['full_ffn_us'] for r in pool44))} for c in traces['cases']]
    old=repo/'results/c138-c135-strong-reanalysis-20260929T2314Z';oldrows=json.loads((old/'layer-call-table.json').read_text())
    cpu=[r for r in oldrows if r['phase']=='decode' and r['device']=='CPU'];oldwork=max(r['first_us'] for r in rows if r['slots']==40)
    intervals=[b for r in cpu for b in r['ready_bounds']]
    # LOAD_END/transfer-return <= commit <= WAIT_END. Tail is an upper uncertainty interval.
    tail=sum(b['wait_end_us']-b['last_transfer_return_us'] for b in intervals)
    coarse=sum(min(oldwork,max(0,b['last_transfer_return_us']-b['wait_start_us'])) for b in intervals)
    denominator=json.loads((old/'analysis.json').read_text())['original_analysis']['trace']['decode_call_duration_s']
    c135={'scope':'slots40 server trace-on 46 decode calls; commit unknown, not production timing',
          'decode_trace_calls_s':denominator,'first_max40_us':oldwork,'wait_barriers':len(intervals),
          'commit_to_wake_tail_upper_s':tail/1e6,'coarse_conditional_percent':100*(coarse+tail)/1e6/denominator,
          'exact_commit_release_scenario':'UNKNOWN','hashes':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (old/'analysis.json',old/'layer-call-table.json')}}
    result={'status':'MEASURED_ISOLATED_CPU_TIMING_CONDITIONAL_ENVELOPE','samples':len(rows),'statistics':stats,'traces_slots44':cases,'server_trace_slots40':c135,
      'economic_gate_percent':5,'pilot_admission':'GO_ONE_BOUNDED_PILOT' if any(c['first_max_observed_scenario']['coarse_percent_including_separate_wake']>=5 for c in cases) else 'NOT_RUN_ECONOMIC_GATE',
      'limitations':['Isolated observed timing range is not a rigorous physical bound on production compute.','Uniform per-expert work/unchanged commits are counterfactual assumptions; first-op setup is not wholly shiftable.','Gross next-router gap caps work but contains unshiftable operations.','All samples retained including fullFFN outlier 9668.734us.','Slots44 C-API and slots40 server denominators remain separate.','Pilot GO means an uncertainty worth a bounded native measurement, not a predicted 120B speedup.']}
    with (out/'timing-envelope.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'pilot_admission':result['pilot_admission'],'c135':c135['coarse_conditional_percent'],'c163_164_first':[c['first_max_observed_scenario']['coarse_percent_including_separate_wake'] for c in cases]}))
