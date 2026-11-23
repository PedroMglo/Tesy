from pathlib import Path
import json,hashlib,csv
from collections import defaultdict
from c152_snapshot_read import snapshot,routes
from c152_journal_validate import validate
from residency_primary_replay import replay
from residency_counterfactual import simulate,conditioned_service,credit
from residency_overhead_analyze import phases
from residency_capture_gate import plan
from c122_trace_validate import union_us
import sys
root=Path(__file__).resolve().parents[1];d=Path(sys.argv[1]).resolve();p=json.loads((d/'protocol.json').read_text());out=[];table=[]
for run in p['runs']:
 cap=Path(run['command'][-1]);e=run['env'];initial=snapshot(cap/'after-prefill.snap');final=snapshot(cap/'final.snap');j=validate(Path(e['TESY_C84_EXPERT_TRACE_FILE']+'.window.trace'),initial=snapshot(cap/'before-warm.snap'));routing=routes(e['TESY_C152_ROUTE_FILE']);rr=replay(initial,final,j['rows'],routing);assert rr['status']=='LOGICAL_REPLAY_MATCHED';candidate,state=simulate(initial,routing,52,44);cf=conditioned_service(j['rows'],j,candidate,initial);cr=credit(j,initial,candidate);t=phases(plan(cap));out.append({'id':run['id'],'replay':rr,'phase_s':t,'counterfactual':{'CPU_slots':52,'GPU_slots':44,'misses':sum(len(x['misses']) for x in candidate),'new_misses':cf['new_miss_count'],**cr,'conditional_decode_percent':cr['conditional_avoided_wait_union_s']/t['decode']*100},'raw_hashes':{k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in [('trace',e['TESY_C84_EXPERT_TRACE_FILE']),('routing',e['TESY_C152_ROUTE_FILE']),('post_prefill_snapshot',cap/'after-prefill.snap'),('final_snapshot',cap/'final.snap')]}})
 event_groups=defaultdict(list);bar_groups=defaultdict(list);pair_groups=defaultdict(list)
 for e in j['rows']:event_groups[(e['call_id'],e['layer'])].append(e)
 for b0 in j['barriers']:bar_groups[(b0['begin']['call_id'],b0['begin']['layer'])].append(b0)
 for kind0 in ('READ_BEGIN','TENSOR_SET_BEGIN','LOAD_BEGIN'):
  for x0,y0 in j['pairs'].get(kind0,[]):pair_groups[(kind0,x0['layer'])].append((x0,y0))
 for call in range(9,58):
  a,b=j['calls'][call]['begin']['mono_us'],j['calls'][call]['end']['mono_us']
  for layer in range(36):
   events=event_groups[(call,layer)];bar=bar_groups[(call,layer)];row={'run':run['id'],'call':call,'layer':layer,'tier':'CPU' if layer<25 else 'GPU','phase':'prefill' if call<11 else 'decode','demands':sum(x['kind']=='DEMAND' for x in events),'resident_hits':sum(x['kind']=='DEMAND' and x['state']==2 for x in events),'misses':sum(x['kind']=='DEMAND' and x['state']==0 for x in events),'loads':sum(x['kind']=='LOAD_BEGIN' for x in events),'victims':sum(x['kind']=='EVICT' for x in events),'barriers':len(bar),'wait_union_us':union_us((x['begin']['mono_us'],x['end']['mono_us']) for x in bar),'last_demand_commit_ready_us':max((x['ready_us'] for x in bar),default=0)}
   for kind,name in [('READ_BEGIN','read'),('TENSOR_SET_BEGIN','set'),('LOAD_BEGIN','load')]:row[name+'_intersect_call_union_us']=union_us((max(a,x['mono_us']),min(b,y['mono_us'])) for x,y in pair_groups[(kind,layer)] if max(a,x['mono_us'])<min(b,y['mono_us']))
   table.append(row)
r={'status':'CPU52_GPU44_POLICY_NO_GO_ON_FROZEN_HOLDOUT_GATE' if any(x['counterfactual']['conditional_decode_percent']<8 or x['counterfactual']['new_misses'] for x in out) else 'CPU52_GPU44_CONDITIONAL_HOLDOUT_GATE_PASS','holdouts':out,'gate':'>=8% conditioned decode reduction on BOTH frozen holdouts; no newly required unmeasured service','authority':'LOGICAL_REPLAY_MATCHED plus COUNTERFACTUAL_SIMULATED/TEMPORAL_BOUND_CONDITIONAL; no new physical profile timing','scope':'Actual post-prefill snapshots of direct C API probe,47 forwards. Primary decode remap reproduced independently; wave/prefill replay and server-state bridge NOT_RUN. Not an upper bound rejecting all static/adaptive residency or other memory envelopes','next_action':'Conditional upstream mmap observer/phase diagnostic; selectedCPU52 rejected without implementation or holdout retuning'}
(d/'residency-decision.json').open('x').write(json.dumps(r,indent=2)+'\n')
with (d/'layer-call-table.csv').open('x') as f:w=csv.DictWriter(f,fieldnames=table[0]);w.writeheader();w.writerows(table)
manifest={str(x.relative_to(d/'raw')):{'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in (d/'raw').rglob('*') if x.is_file()};(d/'raw-manifest.json').open('x').write(json.dumps({'files':manifest,'total_bytes':sum(x['bytes'] for x in manifest.values())},indent=2)+'\n');print(json.dumps(r))
