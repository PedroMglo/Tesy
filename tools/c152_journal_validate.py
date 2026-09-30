"""Validate publication order, logical commits and asynchronous component intervals."""
import csv
from collections import defaultdict
from pathlib import Path
from c122_trace_validate import PAIRS,union_us

HEADER='kind seq mono_us layer expert slot victim n_tokens wave state logical_bytes call_id generation component work_id'.split()
KINDS=set(PAIRS)|set(PAIRS.values())|{'DEMAND','PRELOAD','ENQUEUE','DEQUEUE','RESERVE','EVICT',
        'BARRIER_SLOT','STALE_WORK','RESIDENT_COMMIT','COMMIT_ERROR','REMAP_DONE','WAVE_DONE'}
WORKER={'READ_BEGIN','READ_END','TENSOR_SET_BEGIN','TENSOR_SET_RETURN','LOAD_BEGIN','LOAD_END','DEQUEUE',
        'STALE_WORK','RESIDENT_COMMIT'}

def validate(path, *, physical=True):
    path=Path(path)
    if not 0<path.stat().st_size<=64*1024*1024:raise ValueError('journal size')
    lines=path.read_text().splitlines()
    if lines[0]!='#c152-expert-snapshot-v1':raise ValueError('journal schema')
    at=next((i for i,x in enumerate(lines) if x.startswith('kind\t')),None)
    if at is None or lines[at].split('\t')!=HEADER:raise ValueError('journal columns')
    layers={}
    for line in lines[1:at]:
        if not line.startswith('L\t'):continue
        _,i,size,device=line.split('\t');i=int(i);size=int(size)
        if i in layers or not 0<=i<36 or size!=13219200 or device!=('CPU' if i<25 else 'CUDA0'):raise ValueError('real layer/components map')
        layers[i]={'bytes':size,'device':device}
    if physical and set(layers)!=set(range(36)):raise ValueError('missing physical layers')
    rows=[]
    for i,line in enumerate(lines[at+1:-1]):
        fields=line.split('\t')
        if len(fields)!=len(HEADER):raise ValueError('journal row')
        e={k:(v if k=='kind' else int(v)) for k,v in zip(HEADER,fields)}
        if e['seq']!=i or e['kind'] not in KINDS or e['mono_us']<0 or e['call_id']<1 or not -1<=e['layer']<36:raise ValueError('publication/kind/identity')
        if e['kind']=='COMMIT_ERROR':raise ValueError('commit error')
        rows.append(e)
    if lines[-1].split('\t')!=['#end',str(len(rows)),'0']:raise ValueError('overflow/footer')
    pending={};pairs=defaultdict(list);calls={}
    inverse={v:k for k,v in PAIRS.items()}
    def key(e):return (e['call_id'],e['layer'],e['expert'],e['slot'],e['generation'],e['component'],e['wave'])
    for e in rows:
        k=key(e);kind=e['kind']
        if kind in PAIRS:
            if (kind,k) in pending:raise ValueError('duplicate begin')
            pending[(kind,k)]=e
        elif kind in inverse:
            begin=inverse[kind];a=pending.pop((begin,k),None)
            if a is None or e['mono_us']<a['mono_us']:raise ValueError('orphan/negative/duplicate end')
            pairs[begin].append((a,e))
            if begin=='CALL_BEGIN':
                cid=e['call_id']
                if cid in calls:raise ValueError('duplicate call')
                calls[cid]={'begin':a,'end':e}
    if pending:raise ValueError('unfinished begin')
    previous=None
    for cid,c in sorted(calls.items()):
        if previous and c['begin']['mono_us']<previous:raise ValueError('overlapping synchronous calls')
        previous=c['end']['mono_us']
    for e in rows:
        if e['call_id'] not in calls:raise ValueError('unknown origin call')
        c=calls[e['call_id']]
        if e['kind'] not in WORKER and not c['begin']['mono_us']<=e['mono_us']<=c['end']['mono_us']:raise ValueError('synchronous event outside call')
    loads={}
    for a,b in pairs['LOAD_BEGIN']:
        k=key(a)[:5]
        if k in loads:raise ValueError('duplicate load generation')
        loads[k]=(a,b)
    components=defaultdict(dict)
    for begin in ('READ_BEGIN','TENSOR_SET_BEGIN'):
        for a,b in pairs[begin]:
            k=key(a)[:5];parent=loads.get(k)
            if parent is None or not parent[0]['mono_us']<=a['mono_us']<=b['mono_us']<=parent[1]['mono_us']:raise ValueError('component outside load')
            if a['logical_bytes']!=b['logical_bytes'] or a['component'] not in (0,1,2):raise ValueError('component bytes/index')
            ck=(a['component'],begin)
            if ck in components[k]:raise ValueError('duplicate component')
            components[k][ck]=(a,b)
    if physical:
        for k,(a,b) in loads.items():
            if a['logical_bytes']!=13219200 or b['logical_bytes']!=13219200 or set(components[k])!={(j,t) for j in range(3) for t in ('READ_BEGIN','TENSOR_SET_BEGIN')}:raise ValueError('load component cardinality/bytes')
            for j in range(3):
                read,set_=components[k][(j,'READ_BEGIN')],components[k][(j,'TENSOR_SET_BEGIN')]
                if read[1]['mono_us']>set_[0]['mono_us'] or read[0]['logical_bytes']!=4406400 or set_[0]['logical_bytes']!=4406400:raise ValueError('READ->SET chronology/canonical bytes')
    enqueued={};claimed={};committed={};stale={}
    for e in rows:
        k=e['work_id'];kind=e['kind']
        if kind not in ('ENQUEUE','DEQUEUE','RESIDENT_COMMIT','STALE_WORK'):continue
        if k<=0:raise ValueError('work ID absent')
        if kind=='ENQUEUE':
            if k in enqueued:raise ValueError('duplicate enqueue work')
            enqueued[k]=e;continue
        q=enqueued.get(k)
        if q is None or any(e[f]!=q[f] for f in ('layer','expert','slot','generation','call_id')):raise ValueError('work origin/generation identity')
        if kind=='DEQUEUE':
            if k in claimed or k in stale:raise ValueError('duplicate claim')
            if not 0<=e['component']<18:raise ValueError('worker index')
            claimed[k]=e
        elif kind=='STALE_WORK':
            if k in stale or k in claimed:raise ValueError('duplicate stale work')
            stale[k]=e
        else:
            claim=claimed.get(k);load=loads.get(key(e)[:5])
            if k in committed or claim is None or load is None or e['state']!=2 or e['component']!=claim['component'] or e['mono_us']<load[1]['mono_us']:raise ValueError('resident commit/return identity')
            committed[k]=e
    if set(claimed)!=set(committed):raise ValueError('missing resident commit')
    slots=defaultdict(list);barriers=[];commit_generations=defaultdict(list)
    for e in committed.values():commit_generations[(e['layer'],e['expert'],e['slot'],e['generation'])].append(e)
    for e in rows:
        k=(e['call_id'],e['layer'],e['wave'])
        if e['kind']=='BARRIER_SLOT':
            if e['generation']<=0 or e['state'] not in (1,2):raise ValueError('barrier generation/state')
            slots[k].append(e)
        elif e['kind']=='WAIT_BEGIN':
            group=slots.pop(k,[])
            if not group or len({(x['slot'],x['generation']) for x in group})!=len(group):raise ValueError('barrier demand slots absent/duplicate')
            end=next((b for a,b in pairs['WAIT_BEGIN'] if a['seq']==e['seq']),None)
            if end is None:raise ValueError('barrier end absent')
            ready=[]
            for x in group:
                if x['state']==2:continue
                candidates=commit_generations[(x['layer'],x['expert'],x['slot'],x['generation'])]
                found=[c for c in candidates if x['seq']<c['seq']<end['seq'] and c['mono_us']<=end['mono_us']]
                if len(found)!=1:raise ValueError('barrier missing/late demanded resident commit')
                ready.append(found[0])
            barriers.append({'begin':e,'end':end,'demands':group,'blocking_commits':ready,
                'ready_us':max((x['mono_us'] for x in ready),default=e['mono_us'])})
    if any(slots.values()):raise ValueError('barrier slots without wait')
    # No global monotonic timestamp requirement: worker spans are published retrospectively.
    return {'layers':layers,'rows':rows,'calls':calls,'pairs':dict(pairs),'commits':committed,
            'loads':loads,'barriers':barriers,'queue_tail_work_ids':sorted(set(enqueued)-set(committed)-set(stale)),
            'worker_union_us':union_us((a['mono_us'],b['mono_us']) for a,b in pairs['LOAD_BEGIN'])}
