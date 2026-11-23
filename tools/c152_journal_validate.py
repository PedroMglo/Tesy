"""Strict logical journal gates. Publication sequence and causal timestamps are distinct."""
from collections import defaultdict
from pathlib import Path
from c122_trace_validate import PAIRS,union_us

HEADER='kind seq mono_us layer expert slot victim n_tokens wave state logical_bytes call_id generation component work_id'.split()
KINDS=set(PAIRS)|set(PAIRS.values())|{'DEMAND','PRELOAD','ENQUEUE','DEQUEUE','RESERVE','EVICT','BARRIER_SLOT','STALE_WORK','CANCEL_WORK','RESIDENT_COMMIT','COMMIT_ERROR','REMAP_DONE','WAVE_DONE'}
WORKER={'READ_BEGIN','READ_END','TENSOR_SET_BEGIN','TENSOR_SET_RETURN','LOAD_BEGIN','LOAD_END','DEQUEUE','STALE_WORK','CANCEL_WORK','RESIDENT_COMMIT'}
WORK_KINDS=WORKER|{'ENQUEUE'}

def validate(path,*,physical=True,initial=None,max_bytes=64*1024*1024):
    path=Path(path)
    if path.name.endswith('.partial') or not 0<path.stat().st_size<=max_bytes:raise ValueError('journal incomplete/size')
    lines=path.read_text().splitlines()
    if lines[0] not in ('#c152-expert-snapshot-v1','#c156-expert-snapshot-v2'):raise ValueError('journal schema')
    if physical and lines[0]!='#c156-expert-snapshot-v2':raise ValueError('physical journal requires qualified schema')
    at=next((i for i,x in enumerate(lines) if x.startswith('kind\t')),None)
    if at is None or lines[at].split('\t')!=HEADER:raise ValueError('journal columns')
    layers={};requests=[]
    for line in lines[1:at]:
        if line.startswith('#'):continue
        if line.startswith('L\t'):
            _,i,size,device=line.split('\t');i=int(i);size=int(size)
            if i in layers or not 0<=i<36 or size<=0 or device!=('CPU' if i<25 else 'CUDA0'):raise ValueError('layer metadata')
            if physical and size!=13219200:raise ValueError('canonical expert bytes')
            layers[i]={'bytes':size,'device':device}
        elif line.startswith('R\t'):
            _,request,begin,end=line.split('\t');requests.append(tuple(map(int,(request,begin,end))))
        else:raise ValueError('unknown metadata')
    if physical and set(layers)!=set(range(36)):raise ValueError('missing physical layers')
    rows=[];start_seq=initial['transition_seq'] if initial else 0
    for i,line in enumerate(lines[at+1:-1]):
        fields=line.split('\t')
        if len(fields)!=len(HEADER):raise ValueError('journal row')
        e={k:(v if k=='kind' else int(v)) for k,v in zip(HEADER,fields)}
        if e['seq']!=start_seq+i or e['kind'] not in KINDS or e['mono_us']<0 or e['call_id']<1 or not -1<=e['layer']<36 or e['logical_bytes']<0:raise ValueError('publication/kind/identity')
        if e['kind']=='COMMIT_ERROR':raise ValueError('commit error')
        if e['kind'].startswith('CALL_'):
            if e['layer']!=-1 or e['n_tokens']<=0 or e['expert']<0 or e['slot']-e['expert']+1!=e['n_tokens']:raise ValueError('call shape/positions')
        else:
            if physical and e['layer'] not in layers or e['layer']<0:raise ValueError('event layer')
            if e['state'] not in (-1,0,1,2):raise ValueError('state enumeration')
        if e['kind'] in WORK_KINDS and (e['work_id']<=0 or e['generation']<=0 or not 0<=e['expert']<128 or not 0<=e['slot']<128):raise ValueError('work/generation/component identity')
        if e['kind']=='DEMAND' and (not 0<=e['expert']<128 or e['state'] not in (0,1,2) or e['state']==0 and e['slot']!=-1 or e['state']!=0 and (e['slot']<0 or e['generation']<=0)):raise ValueError('demand identity')
        rows.append(e)
    if not rows or lines[-1].split('\t')!=['#end',str(start_seq+len(rows)),'0']:raise ValueError('overflow/footer')
    if lines[0]=='#c156-expert-snapshot-v2':
        if not requests:raise ValueError('request ranges missing')
        previous=start_seq;last_request=0
        for req,a,b in requests:
            if req<=last_request or a!=previous or b<a or b>start_seq+len(rows):raise ValueError('request range identity/cardinality')
            if sum(len(x.encode())+1 for x in lines[at+1+a-start_seq:at+1+b-start_seq])>32*1024*1024:raise ValueError('serialized request overflow')
            previous=b;last_request=req
        if previous!=start_seq+len(rows):raise ValueError('request range coverage')
    pending={};pairs=defaultdict(list);calls={};ends={}
    inverse={v:k for k,v in PAIRS.items()}
    def key(e):return tuple(e[x] for x in ('call_id','layer','expert','slot','generation','component','wave','work_id'))
    def load_key(e):return tuple(e[x] for x in ('call_id','layer','expert','slot','generation','work_id'))
    for e in rows:
        k=key(e);kind=e['kind']
        if kind in PAIRS:
            if (kind,k) in pending:raise ValueError('duplicate begin')
            pending[(kind,k)]=e
        elif kind in inverse:
            begin=inverse[kind];a=pending.pop((begin,k),None)
            if a is None or e['mono_us']<a['mono_us']:raise ValueError('orphan/negative/duplicate end')
            if any(a[f]!=e[f] for f in ('logical_bytes','n_tokens','state','victim')):raise ValueError('pair metadata mismatch')
            pairs[begin].append((a,e));ends[a['seq']]=e
            if begin=='CALL_BEGIN':
                cid=e['call_id']
                if cid in calls:raise ValueError('duplicate call')
                calls[cid]={'begin':a,'end':e}
    if pending or not calls:raise ValueError('unfinished begin/call')
    previous=None;expected=min(calls)
    for cid,c in sorted(calls.items()):
        if cid!=expected:raise ValueError('missing call')
        expected=cid+1
        if previous is not None and c['begin']['mono_us']<previous:raise ValueError('overlapping synchronous calls')
        previous=c['end']['mono_us']
    seeded_ids={w['work_id'] for w in (initial['queue']+[w for w in initial['owned'] if w['phase']])} if initial else set()
    for e in rows:
        if e['call_id'] not in calls:
            if e['kind'] not in WORKER or e['work_id'] not in seeded_ids:raise ValueError('unknown origin call')
            continue
        c=calls[e['call_id']]
        if e['kind'] not in WORKER and not c['begin']['mono_us']<=e['mono_us']<=c['end']['mono_us']:raise ValueError('synchronous event outside call')
    loads={};components=defaultdict(dict)
    for a,b in pairs['LOAD_BEGIN']:
        k=load_key(a)
        if k in loads or a['component']!=-1:raise ValueError('duplicate load/component')
        loads[k]=(a,b)
    for begin in ('READ_BEGIN','TENSOR_SET_BEGIN'):
        for a,b in pairs[begin]:
            k=load_key(a);parent=loads.get(k)
            if parent is None or not parent[0]['mono_us']<=a['mono_us']<=b['mono_us']<=parent[1]['mono_us']:raise ValueError('component outside load')
            if a['logical_bytes']<=0 or a['component'] not in (0,1,2):raise ValueError('component bytes/index')
            ck=(a['component'],begin)
            if ck in components[k]:raise ValueError('duplicate component')
            components[k][ck]=(a,b)
    for k,(a,b) in loads.items():
        if not physical and a['logical_bytes']==0 and not components[k]:continue # native no-weight worker fixture
        if a['layer'] not in layers or a['logical_bytes']!=layers[a['layer']]['bytes'] or set(components[k])!={(j,t) for j in range(3) for t in ('READ_BEGIN','TENSOR_SET_BEGIN')}:raise ValueError('load component cardinality/bytes')
        previous=a['mono_us'];total=0
        for j in range(3):
            read,set_=components[k][(j,'READ_BEGIN')],components[k][(j,'TENSOR_SET_BEGIN')]
            if not previous<=read[0]['mono_us']<=read[1]['mono_us']<=set_[0]['mono_us']<=set_[1]['mono_us']:raise ValueError('READ->SET chronology')
            if read[0]['logical_bytes']!=set_[0]['logical_bytes'] or physical and read[0]['logical_bytes']!=4406400:raise ValueError('canonical component bytes')
            total+=read[0]['logical_bytes'];previous=set_[1]['mono_us']
        if total!=a['logical_bytes']:raise ValueError('component bytes sum')
    enqueued={};claimed={};committed={};stale={};cancelled={}
    if initial:
        for w in initial['queue']+[w for w in initial['owned'] if w['phase']]:
            e={**w,'call_id':w['origin_call'],'mono_us':w['enqueue_us'],'component':w.get('worker',-1)}
            if w['work_id'] in enqueued:raise ValueError('initial duplicate work')
            enqueued[w['work_id']]=e
            if w.get('phase'):claimed[w['work_id']]=e
    for e in rows:
        k=e['work_id'];kind=e['kind']
        if kind not in ('ENQUEUE','DEQUEUE','RESIDENT_COMMIT','STALE_WORK','CANCEL_WORK'):continue
        if kind=='ENQUEUE':
            if k in enqueued:raise ValueError('duplicate enqueue work')
            enqueued[k]=e;continue
        q=enqueued.get(k)
        if q is None or any(e[f]!=q[f] for f in ('layer','expert','slot','generation','call_id')) or e['mono_us']<q['mono_us']:raise ValueError('work origin/generation/chronology')
        if kind=='DEQUEUE':
            if k in claimed or k in stale or k in cancelled or not 0<=e['component']<18:raise ValueError('duplicate/invalid claim')
            claimed[k]=e
        elif kind in ('STALE_WORK','CANCEL_WORK'):
            if k in stale or k in claimed or k in committed or k in cancelled:raise ValueError('duplicate stale/cancel work')
            (stale if kind=='STALE_WORK' else cancelled)[k]=e
        else:
            claim=claimed.get(k);load=loads.get(load_key(e))
            if k in committed or claim is None or load is None or e['state']!=2 or e['component']!=claim['component'] or e['mono_us']<load[1]['mono_us'] or load[0]['mono_us']<q['mono_us']:raise ValueError('resident commit/return identity')
            if k not in seeded_ids and load[0]['mono_us']<claim['mono_us']:raise ValueError('load before claim')
            committed[k]=e
    if set(claimed)!=set(committed) or {k[-1] for k in loads}!=set(committed):raise ValueError('missing resident commit/load')
    slots=defaultdict(list);barriers=[];commit_generations=defaultdict(list)
    for e in committed.values():commit_generations[tuple(e[f] for f in ('layer','expert','slot','generation'))].append(e)
    for e in rows:
        k=(e['call_id'],e['layer'],e['wave'])
        if e['kind']=='BARRIER_SLOT':
            if e['generation']<=0 or e['state'] not in (1,2) or not 0<=e['expert']<128 or not 0<=e['slot']<128:raise ValueError('barrier generation/state')
            slots[k].append(e)
        elif e['kind']=='WAIT_BEGIN':
            group=slots.pop(k,[]);end=ends[e['seq']]
            if not group or len({(x['slot'],x['generation']) for x in group})!=len(group):raise ValueError('barrier demand slots absent/duplicate')
            ready=[]
            for x in group:
                if x['state']==2:continue
                found=[c for c in commit_generations[tuple(x[f] for f in ('layer','expert','slot','generation'))] if x['seq']<c['seq']<end['seq'] and c['mono_us']<=end['mono_us']]
                if len(found)!=1:raise ValueError('barrier missing/late demanded resident commit')
                ready.append(found[0])
            barriers.append({'begin':e,'end':end,'demands':group,'blocking_commits':ready,'ready_us':max((x['mono_us'] for x in ready),default=e['mono_us'])})
    if any(slots.values()):raise ValueError('barrier slots without wait')
    return {'layers':layers,'requests':requests,'rows':rows,'calls':calls,'pairs':dict(pairs),'commits':committed,'loads':loads,'barriers':barriers,'queue_tail_work_ids':sorted(set(enqueued)-set(committed)-set(stale)-set(cancelled)),'cancelled_work_ids':sorted(cancelled),'worker_union_us':union_us((a['mono_us'],b['mono_us']) for a,b in pairs['LOAD_BEGIN'])}
