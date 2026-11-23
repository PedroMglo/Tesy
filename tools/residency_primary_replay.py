"""Remap policy generated from routing and a real post-prefill logical snapshot.
Worker dequeue/commit order and enqueue timestamps are external observations.
No journal victim or reservation is applied as a policy decision.
Prefill wave planning is outside this decode-window replay's claim.
"""
import copy
from collections import deque
from c152_snapshot_read import VECTORS,WORK

class ReplayMismatch(ValueError):pass

def replay(initial,final,rows,routing):
 s=copy.deepcopy(initial);expected=deque();contexts={};pending=None;stats={'demands':0,'hits':0,'misses':0,'generated_victims':0,'loads':0,'commits':0,'barriers':0}
 queue=deque(s['queue']);owners={w['worker']:w for w in s['owned'] if w['phase']};route_at={}
 for r in routing:
  if initial['transition_seq']<=r['transition_seq']<final['transition_seq']:route_at.setdefault(r['transition_seq'],[]).append(r)
 def need(ok,why,e):
  if not ok:raise ReplayMismatch(f"seq={e.get('seq')} call={e.get('call_id')} layer={e.get('layer')} {why}")
 def expect(kind,**fields):expected.append({'kind':kind,**fields})
 def victim(sl):
  allowed=[i for i in range(sl['n_slots']) if not sl['keep'][i] and sl['slot_state'][i]!=1]
  empty=[i for i in allowed if sl['slot_state'][i]==0]
  return empty[0] if empty else min(allowed,key=lambda i:(sl['route_hotness'][sl['slot_expert'][i]],sl['slot_last_use'][i],i)) if allowed else -1
 def enqueue(sl,expert,slot,call):
  s['next_work_id']+=1
  w={'layer':sl['layer'],'expert':expert,'slot':slot,'generation':sl['slot_gen'][slot],'origin_call':call,'enqueue_us':None,'work_id':s['next_work_id']};queue.append(w)
  expect('ENQUEUE',layer=sl['layer'],expert=expert,slot=slot,generation=w['generation'],call_id=call,work_id=w['work_id'])
 def reserve(sl,expert,slot,call):
  prior=sl['slot_expert'][slot]
  if prior>=0:
   expect('EVICT',layer=sl['layer'],expert=prior,slot=slot,victim=expert,state=sl['slot_state'][slot],generation=sl['slot_gen'][slot]);sl['expert_slot'][prior]=-1;stats['generated_victims']+=1
  sl['slot_expert'][slot]=expert;sl['slot_state'][slot]=1;sl['slot_gen'][slot]+=1;sl['use_counter']+=1;sl['slot_last_use'][slot]=sl['use_counter'];sl['expert_slot'][expert]=slot;sl['seen'][expert]=1
  expect('RESERVE',layer=sl['layer'],expert=expert,slot=slot,state=1,generation=sl['slot_gen'][slot]);enqueue(sl,expert,slot,call)
  sl['keep'][slot]=1;sl['demand_slots'].append(slot)
 def route(r,e):
  need(r['mode']==0,'REPLAY_WAVE_SCOPE_UNQUALIFIED',e)
  need(r['n_calls']==s['n_calls']+1,'global remap counter',e);s['n_calls']+=1
  sl=s['layers'][r['layer']];uniq=list(dict.fromkeys(r['ids']));need(len(uniq)<=sl['n_slots'],'route capacity',e)
  sl['uniq']=uniq;sl['touched']=[int(i in uniq) for i in range(128)]
  for expert in uniq:
   if sl['route_hotness'][expert]<2**32-2:sl['route_hotness'][expert]+=1
  if s['hot_decay_interval'] and s['n_calls']%s['hot_decay_interval']==0:
   for x in s['layers']:
    if x:x['route_hotness']=[v>>1 for v in x['route_hotness']]
  sl['keep']=[0]*sl['n_slots'];sl['demand_slots']=[]
  contexts[(r['call_id'],r['layer'])]={'route':r,'remaining':deque(uniq),'waited':False,'barrier':0,'completed':False}
 selected=[e for e in rows if initial['transition_seq']<=e['seq']<final['transition_seq']]
 for e in selected:
  for r in route_at.pop(e['seq'],[]):route(r,e)
  kind=e['kind'];sl=s['layers'][e['layer']] if e['layer']>=0 else None
  if pending and kind in ('EVICT','RESERVE'):
   li,expert,call=pending;v=victim(s['layers'][li]);need(v>=0,'victim unavailable after wake',e);reserve(s['layers'][li],expert,v,call);pending=None
  if expected:
   want=expected.popleft();need(all(e[k]==v for k,v in want.items()),'generated transition '+str(want),e)
   if kind=='ENQUEUE':queue[-1]['enqueue_us']=e['mono_us']
   continue
  context=contexts.get((e['call_id'],e['layer']))
  if kind=='DEMAND':
   need(context is not None and context['remaining'],'missing routing demand',e);expert=context['remaining'].popleft();slot=sl['expert_slot'][expert];state=sl['slot_state'][slot] if slot>=0 else 0;generation=sl['slot_gen'][slot] if slot>=0 else 0
   need((e['expert'],e['slot'],e['state'],e['generation'])==(expert,slot,state,generation),'autonomous demand hit/miss/state',e);stats['demands']+=1
   if slot>=0:
    stats['hits']+=1
    if state==1:enqueue(sl,expert,slot,e['call_id']);context['waited']=True
    sl['keep'][slot]=1;sl['demand_slots'].append(slot)
   else:
    stats['misses']+=1;context['waited']=True;v=victim(sl)
    if v<0:pending=(e['layer'],expert,e['call_id'])
    else:reserve(sl,expert,v,e['call_id'])
  elif kind in ('DEQUEUE','STALE_WORK','CANCEL_WORK'):
   need(bool(queue),'queue empty',e);w=queue.popleft();need(all(e[k]==w[q] for k,q in [('layer','layer'),('expert','expert'),('slot','slot'),('generation','generation'),('work_id','work_id'),('call_id','origin_call')]),'FIFO work identity',e)
   stale=w['generation']!=sl['slot_gen'][w['slot']] or sl['slot_state'][w['slot']]!=1 or sl['slot_expert'][w['slot']]!=w['expert'] or sl['slot_claimed'][w['slot']]
   if kind=='DEQUEUE':
    need(not stale,'claimed stale work',e);worker=e['component'];need(worker not in owners,'worker busy',e);sl['slot_claimed'][w['slot']]=1;owners[worker]={'worker':worker,'phase':1,**w}
   elif kind=='STALE_WORK':need(stale,'valid work incorrectly stale',e)
  elif kind=='RESIDENT_COMMIT':
   worker=e['component'];need(worker in owners,'worker completion missing owner',e);w=owners.pop(worker);need(all(e[k]==w[q] for k,q in [('layer','layer'),('expert','expert'),('slot','slot'),('generation','generation'),('work_id','work_id')]),'commit generation identity',e);need(sl['slot_claimed'][e['slot']]==1,'commit unclaimed slot',e);sl['slot_claimed'][e['slot']]=0;sl['slot_state'][e['slot']]=2;stats['commits']+=1
  elif kind=='BARRIER_SLOT':
   need(context is not None and context['waited'] and not context['remaining'],'barrier before demands',e);index=context['barrier'];need(index<len(sl['demand_slots']),'extra barrier slot',e);slot=sl['demand_slots'][index];need((e['slot'],e['expert'],e['generation'],e['state'])==(slot,sl['slot_expert'][slot],sl['slot_gen'][slot],sl['slot_state'][slot]),'required barrier generation',e);context['barrier']+=1
  elif kind=='WAIT_BEGIN':
   need(context is not None and context['barrier']==len(sl['demand_slots']),'barrier cardinality',e);stats['barriers']+=1
  elif kind=='WAIT_END':need(all(sl['slot_state'][i]==2 for i in sl['demand_slots']),'wait returned before committed readiness',e)
  elif kind=='REMAP_DONE':
   need(context is not None and not context['remaining'] and not context['completed'],'remap cardinality/duplicate',e)
   for expert in context['route']['ids']:
    slot=sl['expert_slot'][expert];need(slot>=0 and sl['slot_state'][slot]==2,'unready output mapping',e);sl['use_counter']+=1;sl['slot_last_use'][slot]=sl['use_counter']
   context['completed']=True
  elif kind=='LOAD_BEGIN':stats['loads']+=1
  elif kind in ('LOAD_END','READ_BEGIN','READ_END','TENSOR_SET_BEGIN','TENSOR_SET_RETURN','CALL_BEGIN','CALL_END','MUTEX_WAIT_BEGIN','MUTEX_WAIT_END','VICTIM_WAIT_BEGIN','VICTIM_WAIT_END'):pass
  else:need(False,'unsupported decode replay event '+kind,e)
 need(not expected and pending is None and not route_at,'unfinished generated transitions',selected[-1])
 need(all(c['completed'] for c in contexts.values()),'unfinished remap',selected[-1])
 differences=[]
 for name in ('n_calls','hot_decay_interval','next_work_id'):
  if s[name]!=final[name]:differences.append({'field':name,'predicted':s[name],'observed':final[name]})
 for i,(a,b) in enumerate(zip(s['layers'],final['layers'])):
  if a is None and b is None:continue
  for name in (*VECTORS,'use_counter','n_slots','plan_capacity','n_waves','next_wave'):
   if a[name]!=b[name]:differences.append({'layer':i,'field':name,'predicted':a[name],'observed':b[name]})
 need(list(queue)==final['queue'],'final pending queue',selected[-1])
 observed={w['worker']:w for w in final['owned'] if w['phase']}
 need(set(owners)==set(observed),'final worker set',selected[-1])
 for worker,w in owners.items():need(all(w[k]==observed[worker][k] for k in WORK),'final owned work',selected[-1])
 return {'status':'LOGICAL_REPLAY_MATCHED' if not differences else 'REPLAY_STATE_MISMATCH','differences':differences,'statistics':stats,'remap_invocations':len(contexts),'scope':'Actual snapshot to final snapshot, mode0 remap only; observed external worker ordering; no prefill wave or counterfactual timing qualification'}
