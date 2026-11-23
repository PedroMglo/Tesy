"""Fixed routed decode, instantaneous readiness at each barrier, explicit seed.
No prefill counterfactual or timing prediction; new slots start empty.
"""
import copy

def simulate(seed,routing,cpu_slots=44,gpu_slots=44,victim_policy="hotness"):
 if seed['queue'] or any(w['phase'] for w in seed['owned']) or any(1 in l['slot_state'] for l in seed['layers']):raise ValueError('counterfactual initial asynchronous state requires service model')
 s=copy.deepcopy(seed);out=[]
 for li,l in enumerate(s['layers']):
  quota=cpu_slots if li<25 else gpu_slots
  if quota<l['n_slots']:raise ValueError('shrinking seed not defined')
  for k,zero in [('slot_expert',-1),('slot_state',0),('slot_claimed',0),('slot_gen',0),('slot_last_use',0),('keep',0)]:l[k]+=[zero]*(quota-l['n_slots'])
  l['n_slots']=quota
 for r in routing:
  if r['transition_seq']<seed['transition_seq']:continue
  if r['mode']!=0:raise ValueError('decode remap scope only')
  s['n_calls']+=1;l=s['layers'][r['layer']];uniq=list(dict.fromkeys(r['ids']))
  for e in uniq:
   if l['route_hotness'][e]<2**32-2:l['route_hotness'][e]+=1
  if s['hot_decay_interval'] and s['n_calls']%s['hot_decay_interval']==0:
   for x in s['layers']:x['route_hotness']=[h>>1 for h in x['route_hotness']]
  keep=set();misses=[];victims=[]
  for e in uniq:
   slot=l['expert_slot'][e]
   if slot<0:
    allowed=[i for i in range(l['n_slots']) if i not in keep and l['slot_state'][i]!=1];empty=[i for i in allowed if l['slot_state'][i]==0]
    v=empty[0] if empty else min(allowed,key=lambda i:((l['route_hotness'][l['slot_expert'][i]],l['slot_last_use'][i],i) if victim_policy=='hotness' else (l['slot_last_use'][i],i)))
    old=l['slot_expert'][v]
    if old>=0:l['expert_slot'][old]=-1;victims.append(old)
    l['slot_expert'][v]=e;l['slot_state'][v]=1;l['slot_gen'][v]+=1;l['use_counter']+=1;l['slot_last_use'][v]=l['use_counter'];l['expert_slot'][e]=v;misses.append(e);slot=v
   keep.add(slot)
  for slot in keep:l['slot_state'][slot]=2
  for e in r['ids']:
   slot=l['expert_slot'][e];l['use_counter']+=1;l['slot_last_use'][slot]=l['use_counter']
  out.append({'call_id':r['call_id'],'layer':r['layer'],'misses':misses,'victims':victims})
 return out,s

def conditioned_service(rows,journal,candidate,initial):
 # Only subtract whole waits whose blocking miss set disappears. New misses are
 # not assigned invented times; emit counts and UNKNOWN penalties.
 index={(r['call_id'],r['layer']):r for r in candidate};wait_saved=[];new_misses=[];observed={}
 for e in rows:
  if e['call_id']>initial['call_id'] and e['kind']=='DEMAND' and e['state']==0:observed.setdefault((e['call_id'],e['layer']),set()).add(e['expert'])
 for key,r in index.items():
  added=set(r['misses'])-observed.get(key,set())
  if added:new_misses.append({'call_id':key[0],'layer':key[1],'experts':sorted(added)})
 for b in journal['barriers']:
  e=b['begin'];key=(e['call_id'],e['layer'])
  if key in index and not index[key]['misses']:wait_saved.append((e['mono_us'],b['end']['mono_us']))
 from c122_trace_validate import union_us
 return {'whole_waits_avoided_count':len(wait_saved),'fixed_service_wait_union_credit_s':union_us(wait_saved)/1e6,'new_miss_groups':new_misses,'new_miss_count':sum(len(x['experts']) for x in new_misses),'new_miss_latency_penalty':'UNKNOWN, not zero','scope':'Conditional fixed-route decode from actual44 post-prefill seed, extraCPU slots empty. Instantaneous per-barrier completion affects no later logical decision when no inherited work. Fixed-service whole-wait credit is not an end-to-end speedup or optimistic bound of actual warm48. Changed prefill shapes/state/routes NOT_MODELLED.'}

"""Conditioned exposed wait reduction, with no new service times invented."""
def credit(journal,initial,candidate):
 from c122_trace_validate import union_us
 lookup={(r['call_id'],r['layer']):set(r['misses']) for r in candidate};saved=[];unchanged=0
 for b in journal['barriers']:
  e=b['begin'];key=(e['call_id'],e['layer'])
  if key not in lookup:continue
  old=[x['mono_us'] for x in b['blocking_commits']];remain=[x['mono_us'] for x in b['blocking_commits'] if x['expert'] in lookup[key]]
  if not old:unchanged+=1;continue
  old_ready=max([e['mono_us'],*old]);new_ready=max([e['mono_us'],*remain])
  if not lookup[key]:start=e['mono_us'] # all hits removes observed barrier entirely
  else:start=min(b['end']['mono_us'],new_ready+max(0,b['end']['mono_us']-old_ready)) # preserve measured wake tail
  if start<b['end']['mono_us']:saved.append((start,b['end']['mono_us']))
 return {'conditional_avoided_wait_union_s':union_us(saved)/1e6,'credited_barriers':len(saved),'no_observed_blocking_commit':unchanged,'assumptions':'Fixed routed work and original per-load completion times; unchanged remaining service and wake tail. New misses need independent unknown penalty; original44 seeded extra empty slots is not warm52 state. This is a conditional scenario, not formal optimistic class bound or measured speedup.'}
