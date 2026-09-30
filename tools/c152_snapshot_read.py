"""Strict logical snapshots and full routing, independent of model tensor payloads."""
from pathlib import Path
import struct

VECTORS=('slot_expert','slot_state','slot_claimed','slot_gen','slot_last_use','route_hotness','seen',
         'expert_slot','uniq','touched','keep','demand_slots','expert_wave','plan_pool','pool_used')
HEADER=('request','sequence','call_id','phase','first_pos','last_pos','transition_seq','mono_us',
        'n_calls','hot_decay_interval','workers','error','shutdown','next_work_id','overflow','layer_count')
WORK=('layer','expert','slot','generation','origin_call','enqueue_us','work_id')

def snapshot(path, *, physical=True, expected_hashes=None):
    if Path(path).name.endswith(".partial"):raise ValueError("incomplete snapshot")
    data=Path(path).read_bytes();offset=0
    if len(data)>1024*1024 or len(data)<276 or data[:8]!=b'TESYS152' or data[8:12]!=b'\x04\x03\x02\x01':raise ValueError('snapshot size/magic/endian')
    offset=12
    def integer():
        nonlocal offset
        if offset+8>len(data):raise ValueError('truncated snapshot')
        x=struct.unpack_from('<q',data,offset)[0];offset+=8;return x
    def vector(maximum=128):
        n=integer()
        if not 0<=n<=maximum:raise ValueError('vector bound')
        return [integer() for _ in range(n)]
    def work():return dict(zip(WORK,(integer() for _ in WORK)))
    if integer()!=1:raise ValueError('snapshot version')
    hashes=[]
    for _ in range(4):
        s=data[offset:offset+64].decode('ascii');offset+=64
        if len(s)!=64 or any(c not in '0123456789abcdefABCDEF' for c in s):raise ValueError('snapshot hash')
        hashes.append(s)
    if expected_hashes is not None and hashes!=list(expected_hashes):raise ValueError('snapshot identity hashes')
    out=dict(zip(HEADER,(integer() for _ in HEADER)));out['hashes']=hashes
    if out['overflow'] or out['error'] or not 0<out['layer_count']<=36 or not 0<out['workers']<=18 or out['phase'] not in (0,1,2):raise ValueError('snapshot manager/error/overflow')
    if not 0<=out['first_pos']<=out['last_pos']<8192:raise ValueError('snapshot positions')
    if out['request']<1 or not 0<=out['sequence']<=2 or out['transition_seq']<0 or out['mono_us']<0 or out['n_calls']<0 or out['hot_decay_interval']<0 or out['next_work_id']<0:raise ValueError('manager identity/cardinality')
    layers=[]
    for index in range(out['layer_count']):
        present=integer()
        if present not in (0,1):raise ValueError('layer flag')
        if not present:layers.append(None);continue
        sl=dict(zip(('layer','n_expert','n_slots','use_counter','plan_capacity','n_waves','next_wave','component_count'),(integer() for _ in range(8))))
        if sl['layer']!=index or sl['n_expert']!=128 or not 1<=sl['n_slots']<=128 or not 0<=sl['component_count']<=4:raise ValueError('layer identity')
        components=[]
        for _ in range(sl['component_count']):
            c=dict(zip(('file_index','offset','expert_bytes','type'),(integer() for _ in range(4))))
            c['shape']=[integer() for _ in range(4)];c['stride']=[integer() for _ in range(4)]
            c['device']=data[offset:offset+64].split(b'\0')[0].decode('ascii');offset+=64
            if c['expert_bytes']<=0 or c['offset']<0:raise ValueError('component identity')
            components.append(c)
        sl['components']=components
        for name in VECTORS:sl[name]=vector()
        n=sl['n_slots'];e=sl['n_expert']
        if any(len(sl[k])!=n for k in ('slot_expert','slot_state','slot_claimed','slot_gen','slot_last_use','keep')) or any(len(sl[k])!=e for k in ('route_hotness','seen','expert_slot')):raise ValueError('state vector cardinality')
        if any(x not in (0,1,2) for x in sl['slot_state']) or any(x not in (0,1) for k in ('slot_claimed','seen','keep') for x in sl[k]):raise ValueError('state enumeration')
        mapping=[-1]*e
        for slot,(expert,state,claimed) in enumerate(zip(sl['slot_expert'],sl['slot_state'],sl['slot_claimed'])):
            if state==0:
                if expert!=-1 or claimed:raise ValueError('empty slot identity')
            else:
                if not 0<=expert<e or mapping[expert]!=-1 or claimed and state!=1:raise ValueError('slot/expert/claimed identity')
                mapping[expert]=slot
        if mapping!=sl['expert_slot']:raise ValueError('expert_slot inverse')
        if any(not 0<=x<=2**32-1 for x in sl['route_hotness']) or any(x<0 for x in sl['slot_gen']):raise ValueError('hotness/generation range')
        if any(sl['slot_gen'][i]<1 for i,x in enumerate(sl['slot_state']) if x) or sl['use_counter']<0 or any(not 0<=x<=sl['use_counter'] for x in sl['slot_last_use']):raise ValueError('slot generation/recency')
        if len(set(sl['uniq']))!=len(sl['uniq']) or any(not 0<=x<128 for x in sl['uniq']):raise ValueError('uniq experts')
        if any(not 0<=x<sl['n_slots'] for x in sl['demand_slots']+sl['plan_pool']) or any(x not in (0,1) for x in sl['touched']+sl['pool_used']):raise ValueError('planning state')
        if not 0<=sl['plan_capacity']<=sl['n_slots'] or not -1<=sl['next_wave']<=sl['n_waves']:raise ValueError('wave cardinality')
        layers.append(sl)
    qn=integer()
    if not 0<=qn<=4096:raise ValueError('queue bound')
    out['queue']=[work() for _ in range(qn)];wn=integer()
    if wn!=out['workers']:raise ValueError('worker cardinality')
    out['owned']=[{'worker':integer(),'phase':integer(),**work()} for _ in range(wn)]
    if offset!=len(data):raise ValueError('snapshot trailing bytes')
    out['layers']=layers
    for w in out['queue']+[x for x in out['owned'] if x['phase']]:
        if not 0<=w['layer']<len(layers) or layers[w['layer']] is None or not 0<=w['expert']<128 or not 0<=w['slot']<layers[w['layer']]['n_slots'] or w['generation']<0 or w['work_id']<=0:raise ValueError('work identity')
    active=out['queue']+[w for w in out['owned'] if w['phase']]
    if len({w['work_id'] for w in active})!=len(active) or any(w['work_id']>out['next_work_id'] or w['generation']>layers[w['layer']]['slot_gen'][w['slot']] or w['origin_call']<1 or w['enqueue_us']<0 for w in active):raise ValueError('work generation/counter/duplicate')
    for i,w in enumerate(out['owned']):
        if w['worker']!=i or w['phase'] not in (0,1,2):raise ValueError('owned phase/worker')
        if w['phase']:
            sl=layers[w['layer']];s=w['slot']
            if sl['slot_expert'][s]!=w['expert'] or sl['slot_gen'][s]!=w['generation'] or sl['slot_claimed'][s]!=1:raise ValueError('owned work/slot identity')
    if physical:
        if len(layers)!=36 or any(x is None or x['n_slots']!=44 or x['component_count']!=3 for x in layers):raise ValueError('physical slots44 map')
        for i,sl in enumerate(layers):
            if any(c['device']!=('CPU' if i<25 else 'CUDA0') for c in sl['components']):raise ValueError('actual CPU/GPU placement')
    return out

def routes(path):
    if Path(path).name.endswith('.partial'):raise ValueError('incomplete routing')
    data=Path(path).read_bytes()
    if len(data)%8 or len(data)>8*1024*1024:raise ValueError('routing size/overflow')
    offset=0;out=[]
    while offset<len(data):
        if offset+64>len(data):raise ValueError('route header truncated')
        req,call,layer,mode,ncalls,n,mono,seq=struct.unpack_from('<8q',data,offset);offset+=64
        if req<1 or call<1 or ncalls<1 or mono<0 or seq<0 or not 0<=layer<36 or mode not in (0,1) or not 0<n<=128 or n%4 or offset+8*n>len(data):raise ValueError('route identity/truncation')
        ids=list(struct.unpack_from('<'+'q'*n,data,offset));offset+=8*n
        if any(not 0<=x<128 for x in ids):raise ValueError('route expert')
        for i in range(0,n,4):
            if len(set(ids[i:i+4]))!=4:raise ValueError('duplicate topk within row')
        out.append({'request':req,'call_id':call,'layer':layer,'mode':mode,'n_calls':ncalls,'mono_us':mono,'transition_seq':seq,'ids':ids})
    return out
