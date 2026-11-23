#!/usr/bin/env python3
"""Fixed-trace bounded RAM L2 screen; logical bytes only, no timing claim."""

import csv
import json
from collections import OrderedDict, defaultdict
from pathlib import Path

from c2_gate import GateError, strict_json
from c84_trace_validate import validate as validate_trace, EXPERT_BYTES
from host_resource_policy import GIB
from run_bounded import sha256

REPO=Path(__file__).resolve().parents[1]
SOURCE=REPO/'results/c105-c84-8k-trace-boundary-20260928T2335Z'
TRACE=SOURCE/'raw/c105-c84-trace-on01.expert.trace'
ROOT=REPO/'results/c106-l2-fixed-trace-screen-20260928T2340Z'
BUDGETS=(1*GIB,2*GIB,3*GIB)


def layer_destinations(path):
    """Read device names emitted by the loader, without assuming an ngl split."""
    with path.open(newline='') as stream:
        if stream.readline() != '#c84-expert-demand-v1\n' or \
           stream.readline() != '#layer\tlayer\tlogical_expert_bytes\tbuffer_name\n':
            raise GateError('C106 layer header invalid')
        destinations = {}
        for line in stream:
            if not line.startswith('L\t'):
                break
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 4:
                raise GateError('C106 layer row invalid')
            layer = int(fields[1])
            name = fields[3]
            if layer in destinations or name not in ('CPU', 'CUDA0'):
                raise GateError('C106 layer destination invalid')
            destinations[layer] = 'GPU' if name == 'CUDA0' else 'CPU'
    if set(destinations) != set(range(36)):
        raise GateError('C106 layer destination coverage invalid')
    return destinations


def c105_phase_boundary(events):
    """Strict C105 189+32 call plan; sequence order is publication order."""
    singles = [row for row in events if row['kind'] == 'DEMAND' and row['n_tokens'] == 1]
    if len(singles) != 4 + 32*36*4 or \
       [row['layer'] for row in singles[:4]] != [35]*4:
        raise GateError('C106 final-prefill single-token demand invalid')
    expected = [layer for _token in range(32) for layer in range(36) for _expert in range(4)]
    if [row['layer'] for row in singles[4:]] != expected:
        raise GateError('C106 decode order/cardinality invalid')
    boundary = singles[4]['seq']
    if any(row['n_tokens'] not in (29,32) for row in events
           if row['kind'] == 'DEMAND' and row['seq'] < singles[0]['seq']):
        raise GateError('C106 prefill chunk shape invalid')
    return boundary


def rows(path):
    validate_trace(path)
    with path.open(newline='') as stream:
        if stream.readline()!='#c84-expert-demand-v1\n':raise GateError('C106 header')
        stream.readline()
        line=stream.readline()
        while line.startswith('L\t'):line=stream.readline()
        header=line.rstrip('\n').split('\t')
        for line in stream:
            if line.startswith('#end\t'):break
            fields=line.rstrip('\n').split('\t')
            row=dict(zip(header,fields,strict=True))
            yield {'kind':row['kind'],**{key:int(value) for key,value in row.items() if key!='kind'}}


def simulate(events, slots, mode, *, destinations, phase_of):
    if mode not in ('on_load_lru','on_evict_lru') or type(slots)!=int or slots<=0:
        raise ValueError('invalid C106 simulator setting')
    cache=OrderedDict();demand=defaultdict(lambda:{'misses':0,'saved':0,'hits_primary':0,'inflight_primary':0})
    def insert(key):
        if key in cache:cache.move_to_end(key)
        else:
            cache[key]=None
            if len(cache)>slots:cache.popitem(last=False)
    for row in events:
        key=(row['layer'],row['expert'])
        if row['kind']=='LOAD_END' and mode=='on_load_lru':insert(key)
        if row['kind']=='EVICT' and mode=='on_evict_lru' and row['expert']>=0:insert(key)
        if row['kind']!='DEMAND':continue
        phase=phase_of(row)
        destination=destinations[row['layer']]
        record=demand[(phase,destination)]
        if row['state']==0:
            record['misses']+=1
            if key in cache:
                record['saved']+=1
                cache.move_to_end(key)
        elif row['state']==1:record['inflight_primary']+=1
        elif row['state']==2:record['hits_primary']+=1
    return demand


def union_us(intervals):
    total=0;end=None
    for start,stop in sorted(intervals):
        if end is None or start>end:
            total+=stop-start;end=stop
        elif stop>end:
            total+=stop-end;end=stop
    return total


def wait_summary(events, phase_of):
    open_wait={};intervals=defaultdict(list)
    for row in events:
        if row['kind'] not in ('WAIT_BEGIN','WAIT_END'):continue
        key=(row['layer'],row['wave'])
        phase=phase_of(row)
        if row['kind']=='WAIT_BEGIN':open_wait[key]=(row['mono_us'],phase)
        else:
            start,started_phase=open_wait.pop(key)
            intervals[started_phase if started_phase == phase else 'UNKNOWN'].append((start,row['mono_us']))
    if open_wait:raise GateError('C106 open wait')
    return {phase:{'wait_intervals':len(value),'union_s':union_us(value)/1e6,
                   'sum_s':sum(b-a for a,b in value)/1e6}
            for phase,value in intervals.items()}


def main():
    if ROOT.exists():raise GateError('C106 no-replace root exists')
    prior=strict_json((SOURCE/'decision.json').read_text())
    manifest=strict_json((SOURCE/'manifest.json').read_text())
    if prior['status']!='PASS_DIAGNOSTIC_TRACE_NUMERIC_BOUNDARY' or \
       sha256(TRACE)!=manifest['raw_files'][TRACE.name]['sha256']:
        raise GateError('C106 prior trace/decision invalid')
    events=list(rows(TRACE))
    destinations=layer_destinations(TRACE)
    if any(destinations[layer] != ('CPU' if layer < 25 else 'GPU') for layer in range(36)):
        raise GateError('C106 trace placement differs from frozen C105 P12')
    boundary=c105_phase_boundary(events)
    phase_of=lambda row: 'prefill' if row['seq'] < boundary else 'decode'
    wait=wait_summary(events,phase_of)
    scenarios=[]
    for budget in BUDGETS:
        slots=budget//EXPERT_BYTES
        for mode in ('on_load_lru','on_evict_lru'):
            observed=simulate(events,slots,mode,destinations=destinations,phase_of=phase_of)
            phase={}
            for (name,dest),count in sorted(observed.items()):
                miss=count['misses'];saved=count['saved']
                phase.setdefault(name,{})[dest]={**count,
                    'demanded_logical_bytes':miss*EXPERT_BYTES,
                    'saved_logical_bytes':saved*EXPERT_BYTES,
                    'saved_fraction':saved/miss if miss else None}
            total_miss=sum(x['misses'] for x in observed.values())
            total_saved=sum(x['saved'] for x in observed.values())
            scenarios.append({'budget_bytes':budget,'expert_slots':slots,'mode':mode,
                'phase_destination':phase,'total_demand_misses':total_miss,
                'total_saved_demand_misses':total_saved,
                'total_saved_fraction':total_saved/total_miss if total_miss else None})
    ROOT.mkdir()
    result={'schema':'c106-fixed-trace-l2-v1','status':'MODEL_FREE_FIXED_TRACE_SCREEN',
            'evidence_class':'INFERIDO_FROM_MEASURED_TRACE',
            'trace_sha256':sha256(TRACE),'source_decision_sha256':sha256(SOURCE/'decision.json'),
            'trace_events':len(events),'expert_bytes':EXPERT_BYTES,
            'baseline':'C84 primary 32 slots per layer; DEMAND state=0 absent, state=1 loading, state=2 resident',
            'modes':{'on_load_lru':'insert every completed expert load; encoded RAM copy assumed free and retained while primary may still hold it',
                     'on_evict_lru':'insert evicted primary expert; transfer/copy from CPU/GPU to encoded RAM assumed free, optimistic'},
            'budgets_bytes':list(BUDGETS),'scenarios':scenarios,'wait_intervals':wait,
            'limitations':['fixed routed-event sequence with no feedback from L2','logical expert bytes, not physical NVMe traffic or wall-time speedup',
                           'copy/H2D costs, RAM ownership/staging, page cache and equal-memory pool alternative excluded',
                           '189+32 numeric workload only; warm 153-ID session representativeness NOT_RUN',
                           'wait union is diagnostic interval, not proven removable critical-path time'],
            'investment_rule':'Need >=20% demand logical-byte savings in workload target plus exposed wait consistent with >=8% end-to-end gain and equal-memory accounting before prototype',
            'default_changed':False}
    with (ROOT/'analysis.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    print(json.dumps({'status':result['status'],'events':len(events),
        'wait_union_s':{k:v['union_s'] for k,v in wait.items()},
        'scenarios':[(x['budget_bytes']//GIB,x['mode'],round(x['total_saved_fraction'],4)) for x in scenarios]},allow_nan=False))


if __name__=='__main__':main()
