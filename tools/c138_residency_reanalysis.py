#!/usr/bin/env python3
"""Strict C135 reanalysis, temporal intersections and conditional cold LRU/oracle screen."""
import argparse
from collections import Counter, defaultdict, OrderedDict
import json
from pathlib import Path
import sys

from c2_gate import GateError, strict_json
from c122_trace_validate import validate, union_us, PAIRS
from c123_analyze_trace import trace_rows
import c135_analyze_slots40_trace as previous
from run_bounded import sha256


def intersect(spans, windows):
    return [(max(a,x),min(b,y)) for a,b in spans for x,y in windows if max(a,x)<min(b,y)]


def analyze():
    original = previous.analyze()
    path=previous.ROOT_ON/'raw'/f'{previous.ON}.expert.trace'
    parsed=validate(path);layers,rows=trace_rows(path);calls=parsed['calls']
    starts={};pairs=defaultdict(list)
    for e in rows:
        key=(e['call_id'],e['layer'],e['expert'],e['slot'],e['generation'],e['component'],e['wave'])
        if e['kind'] in PAIRS: starts[(e['kind'],key)]=e['mono_us']
        elif e['kind'] in PAIRS.values():
            kind=next(k for k,v in PAIRS.items() if v==e['kind'])
            pairs[(e['call_id'],e['layer'],kind)].append((starts.pop((kind,key)),e['mono_us']))
    table=[];self_evict=[];route={};cpu_loads=gpu_loads=0
    for cid,c in calls.items():
        for layer in range(36):
            ev=[e for e in rows if e['call_id']==cid and e['layer']==layer]
            demands=[e for e in ev if e['kind']=='DEMAND'];loads=[e for e in ev if e['kind']=='LOAD_BEGIN']
            waits=pairs[(cid,layer,'WAIT_BEGIN')]
            if cid>=3:
                if len(demands)!=4 or len({e['expert'] for e in demands})!=4:
                    raise GateError('C135 decode requires four distinct exact demands per layer/call')
                route[(cid,layer)]=[e['expert'] for e in demands]
                if layer<25:cpu_loads+=len(loads)
                else:gpu_loads+=len(loads)
            for e in ev:
                if e['kind']=='EVICT' and e['victim']>=0:
                    future=[d for d in demands if d['seq']>e['seq'] and d['expert']==e['victim']]
                    if future:self_evict.append({'call':cid,'layer':layer,'victim':e['victim'],
                        'evict_seq':e['seq'],'later_demand_seq':future[0]['seq'],'later_state':future[0]['state'],
                        'wait_barriers_in_group':len(waits)})
            windows=[(c['start_us'],c['end_us'])]
            temporal={}
            for kind in ('READ_BEGIN','TENSOR_SET_BEGIN','LOAD_BEGIN','WAIT_BEGIN'):
                # Origin != window: intersect every worker interval of this layer with measured call.
                spans=[span for (origin,il,k),ss in pairs.items() if il==layer and k==kind for span in ss]
                clipped=intersect(spans,windows)
                temporal[kind]={'union_us':union_us(clipped),'worker_sum_us':sum(b-a for a,b in clipped),
                    'intersecting_spans':len(clipped)}
            boundaries=[]
            for wa,wb in waits:
                ends=[b for a,b in pairs[(cid,layer,'LOAD_BEGIN')] if wa<=b<=wb]
                boundaries.append({'wait_start_us':wa,'wait_end_us':wb,
                    'last_transfer_return_us':max(ends) if ends else None,
                    'resident_commit_us':None,
                    'ready_bound':'last transfer return <= commit <= WAIT_END; mutex reacquisition/commit not instrumented'})
            table.append({'call':cid,'phase':'prefill' if cid in (1,2) else 'decode',
                'layer':layer,'device':layers[layer]['device'],'demands':len(demands),
                'states':dict(Counter(e['state'] for e in demands)), 'loads':len(loads),
                'generations':len({(e['slot'],e['generation']) for e in loads}),
                'victims':sum(e['kind']=='EVICT' and e['victim']>=0 for e in ev),
                'wait_barriers':len(waits),'temporal':temporal,'ready_bounds':boundaries})
    if len(route)!=46*36 or sum(map(len,route.values()))!=6624:raise GateError('decode routing incomplete')
    simulations={}
    for name,cpu,gpu in [('uniform40',40,40),('uniform44',44,44),('cpu44_gpu40',44,40),('cpu46_gpu40',46,40)]:
        metrics={}
        for policy in ('lru','offline_min_load_count'):
            counts=Counter()
            for layer in range(36):
                cap=cpu if layer<25 else gpu;seq=[e for cid in range(3,49) for e in route[(cid,layer)]]
                cache=OrderedDict()
                for i,e in enumerate(seq):
                    if e in cache:cache.move_to_end(e);continue
                    counts['CPU' if layer<25 else 'CUDA0']+=1
                    if len(cache)==cap:
                        if policy=='lru':cache.popitem(last=False)
                        else:
                            future=seq[i+1:]
                            victim=max(cache,key=lambda old:future.index(old) if old in future else len(future)+1)
                            del cache[victim]
                    cache[e]=True
            metrics[policy]={'loads_by_tier':dict(counts),'total_loads':sum(counts.values())}
        simulations[name]={'quota_cpu':cpu,'quota_gpu':gpu,
            'expert_copy_bytes_cpu':25*cpu*13219200,'expert_copy_bytes_gpu':11*gpu*13219200,
            'policies':metrics}
    return {'schema':'c138-c135-reanalysis-v1','authority':'MEDIDO_NO_TARGET for trace; SOURCE_AUDITED for backend; ESTIMADO conditional simulations',
        'original_analysis':original,'strong_trace_validation':{'status':'PASS','events':parsed['events'],
            'worker_tails':parsed['worker_tails'],'all_published_raw_manifests_hash_checked':True},
        'decode_routing':{'demands':6624,'calls':46,'layers':36,'sha256':__import__('hashlib').sha256(
            json.dumps({f'{c}:{l}':v for (c,l),v in route.items()},sort_keys=True).encode()).hexdigest()},
        'decode_loads_by_tier':{'CPU':cpu_loads,'CUDA0':gpu_loads},
        'intra_call_evictions_of_later_demand':self_evict,
        'replay_status':'SOURCE_FAITHFUL_PRIMARY_REPLAY_NOT_IDENTIFIABLE_FROM_C135',
        'replay_missing':['initial slot/expert/generation map','initial hotness and use counters','global decay position',
            'full first-request prefill routing/multiplicities','exact RESIDENT commit timestamps'],
        'conditional_cold_simulations':simulations,
        'simulation_contract':'Empty initial cache, sequential fixed authoritative decode routing, per-layer capacity; LRU and oracle min load count only. Not backend replay, warm bound, latency oracle or equal-memory L2 comparison.',
        'layer_call_table':table,
        'limits':['LOAD_END precedes RESIDENT commit. WAIT cannot be assigned in full to every concurrent load.',
            'No optimistic warm benefit bound is established; conditional cold simulations cannot veto physical uniform44.',
            'No new inferencing or trace required for these repairs.']}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);a=ap.parse_args();a.root.mkdir(exist_ok=True)
    result=analyze()
    table=result.pop('layer_call_table')
    for name,value in [('analysis.json',result),('layer-call-table.json',table)]:
        with (a.root/name).open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':'PASS_STRONG_RAW_REVALIDATION','decode_loads':result['decode_loads_by_tier'],
        'intra_call_self_evictions':len(result['intra_call_evictions_of_later_demand'])}))
