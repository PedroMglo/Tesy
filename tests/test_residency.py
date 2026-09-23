import copy
import json
from pathlib import Path

import pytest

from tesy.io import ContractError
from tesy.residency import Replay, parse_trace, profile, replay, union_windows

ROOT=Path(__file__).resolve().parents[1]


def inputs():
    return (json.loads((ROOT/'examples/routing.synthetic.json').read_text()),
            json.loads((ROOT/'examples/synthetic-profile.json').read_text()))


def test_lru_hand_computed_bytes():
    t,p=inputs()
    r=replay(parse_trace(t),p)
    # 0,1,0,1,0,1,2,2 with one GPU object, two RAM objects.
    assert r['stats']['source_request_bytes']==3*64
    assert r['stats']['h2d_payload_bytes']==7*64
    assert r['stats']['demand_gpu_hits']==1
    assert r['stats']['demand_ram_hits']==4
    assert r['gpu_peak_bytes']==64 and r['ram_peak_bytes']==128
    assert r['qualification'] is False and r['physical_io_measured'] is False


@pytest.mark.parametrize('policy',['lru','lfu','transition'])
def test_cache_capacity_and_determinism(policy):
    t,p=inputs()
    a=replay(parse_trace(t),p,policy)
    assert a==replay(parse_trace(t),p,policy)
    assert all(r['ram_used']<=128 and r['gpu_used']<=64 for r in a['ledger'])
    assert a['stats']['useful_prefetch_bytes']+a['unused_or_evicted_prefetch_bytes']==a['stats']['prefetch_h2d_bytes']


def test_ram_bypass_counts_every_gpu_miss():
    t,p=inputs()
    p['ram_cache_bytes']=0
    r=replay(parse_trace(t),p)
    assert r['stats']['source_request_bytes']==r['stats']['h2d_payload_bytes']==448
    assert r['ram_peak_bytes']==0


def test_large_gpu_hit_does_not_require_ram_inclusion():
    t,p=inputs()
    p.update(gpu_cache_bytes=192,gpu_limit_bytes=256,ram_cache_bytes=0)
    r=replay(parse_trace(t),p)
    assert r['stats']['source_request_bytes']==192 and r['stats']['demand_gpu_hits']==5


def test_causal_prefix_unchanged_when_future_changes():
    t,p=inputs()
    u=copy.deepcopy(t)
    u['events'][-1]['experts']=[0]
    a=replay(parse_trace(t),p,'transition')
    b=replay(parse_trace(u),p,'transition')
    assert a['ledger'][:-1]==b['ledger'][:-1]


def test_predictor_no_prefetch_on_unseen_transition():
    t,p=inputs()
    r=replay(parse_trace(t),p,'transition')
    assert r['ledger'][0]['stats']['prefetch_requests']==0
    assert r['ledger'][1]['stats']['prefetch_requests']==0
    assert r['ledger'][2]['stats']['prefetch_requests']==1


def test_union_not_acceptance_and_partial_tail():
    t,p=inputs()
    r=union_windows(parse_trace(t),3)
    assert [w['tokens_in_window'] for w in r['windows']]==[3,3,2]
    assert r['windows'][0]['encoded_union_bytes']==128
    assert r['acceptance_measured'] is False and r['cold_cache_bytes_measured'] is False
    assert 'speedup' not in r


@pytest.mark.parametrize('key,value',[
    ('gpu_cache_bytes',True),('ram_cache_bytes',-1),('staging_bytes',0),
    ('ram_reserve_bytes',300),('gpu_reserve_bytes',300)])
def test_bad_profile(key,value):
    _,p=inputs()
    p[key]=value
    with pytest.raises(ContractError):
        profile(p)


def test_expert_exceeding_gpu_rejected():
    t,p=inputs()
    p['gpu_cache_bytes']=32
    with pytest.raises(ContractError):
        replay(parse_trace(t),p)


@pytest.mark.parametrize('mutation',range(12))
def test_trace_mutations(mutation):
    t,_=inputs()
    if mutation==0: t['extra']=1
    if mutation==1: t['events'][0]['experts']=[0,0]
    if mutation==2: t['events'][1]['step']=0
    if mutation==3: t['events'][1]['token']=3
    if mutation==4: t['events'][0]['experts']=[True]
    if mutation==5: t['events'][0]['experts']=[100]
    if mutation==6: t['experts'].append(t['experts'][0].copy())
    if mutation==7: t['provenance']['route_semantics']='speculative_tree'
    if mutation==8: t['provenance']['kind']='OBSERVED'
    if mutation==9: t['layers']=[0,0]
    if mutation==10: t['events'][0]['layer']=False
    if mutation==11: t['experts'][0]['bytes']=0
    with pytest.raises(ContractError): parse_trace(t)


def test_experts_identified_by_layer():
    t,p=inputs()
    t['layers']=[0,1]
    t['experts'] += [dict(e,layer=1) for e in t['experts']]
    t['events'] = [{'step':i,'token':i//2,'layer':i%2,'experts':[0]} for i in range(4)]
    r=union_windows(parse_trace(t),2)
    assert r['windows'][0]['encoded_union_bytes']==128


def test_unknown_policy():
    t,p=inputs()
    with pytest.raises(ContractError): replay(parse_trace(t),p,'oracle')


def test_exhaustive_small_lru_against_independent_reference():
    from itertools import product
    for seq in product(range(3), repeat=5):
        t,p=inputs()
        t['events']=[{'step':i,'token':i,'layer':0,'experts':[e]} for i,e in enumerate(seq)]
        gpu,ram=[],[]
        source=h2d=0
        for expert in seq:
            if expert in gpu:
                continue
            h2d+=64
            if expert not in ram:
                source+=64
                if len(ram)==2: ram.pop(0)
            else: ram.remove(expert)
            ram.append(expert)
            gpu=[expert]
        r=replay(parse_trace(t),p)
        assert (r['stats']['source_request_bytes'],r['stats']['h2d_payload_bytes'])==(source,h2d)


def test_variable_size_random_budget_and_prefetch_accounting():
    import random
    rng=random.Random(7831)
    for _ in range(100):
        t,p=inputs()
        for i,expert in enumerate(t['experts']): expert['bytes']=[16,32,64][i]
        t['events']=[{'step':i,'token':i,'layer':0,'experts':rng.sample(range(3),rng.randint(1,3))}
                     for i in range(15)]
        for policy in ('lru','lfu','transition'):
            r=replay(parse_trace(t),p,policy)
            assert r['ram_peak_bytes']<=p['ram_cache_bytes']
            assert r['gpu_peak_bytes']<=p['gpu_cache_bytes']
            assert (r['stats']['useful_prefetch_bytes']+r['unused_or_evicted_prefetch_bytes']
                    == r['stats']['prefetch_h2d_bytes'])
