"""Prospective paired instrumentation overhead, fenced direct C API work only."""
import json,statistics,sys
from pathlib import Path
from residency_capture_gate import plan,sha,capture

def phases(rows):
 return {p:sum(int(r['end_us'])-int(r['begin_us']) for r in rows if r['phase']==p)/1e6 for p in ('prefix-warmup','warm-prefill','decode')}
def paired(pairs):
 result={p:[100*(on[p]-off[p])/off[p] for off,on in pairs] for p in ('prefix-warmup','warm-prefill','decode')}
 if len(pairs)!=2:raise ValueError('two independent alternating pairs required')
 med={p:statistics.median(v) for p,v in result.items()}
 return {'paired_overhead_percent':result,'median_overhead_percent':med,'status':'TEMPORAL_OVERHEAD_GATE_PASS' if all(med[p]<=5 for p in med) else 'STATE_COUNTS_ONLY_OVERHEAD_GATE_NO_GO','threshold_percent':5,'scope':'Fenced direct C API prefix/warm-prefill/decode; no witness observer, no output/SSE/first-final claim. Passing threshold alone does not establish causal scheduling neutrality.'}
def analyze(protocol):
 p=json.loads(protocol.read_text());arms=[];byid={};captures=[]
 for run in p['runs']:
  root=Path(run['command'][-1]);rows=plan(root);a={'id':run['id'],'label':run['label'],'phase_s':phases(rows),'logits_sha256':sha(root/'full-logits.f32')};arms.append(a);byid[a['id']]=a
  if run['label']=='on':
   e=run['env'];caps=capture(root,Path(e['TESY_C84_EXPERT_TRACE_FILE']),Path(e['TESY_C152_ROUTE_FILE']),[e['TESY_C152_'+x+'_HASH'] for x in ('MODEL','SOURCE','BUILD','PROFILE')]);captures.append({'id':run['id'],**caps})
 pairs=[]
 for pair in p['pairs']:
  off,on=[byid[i] for i in pair]
  if (off['label'],on['label'])!=('off','on') or off['logits_sha256']!=on['logits_sha256']:raise ValueError('pair same-profile complete logits mismatch')
  pairs.append((off['phase_s'],on['phase_s']))
 r={**paired(pairs),'arms':arms,'captures':captures,'numeric':'ALL_57_FULL_LOGIT_ROWS_BITWISE_PER_PAIR','next_action':'Logical replay and two frozen holdout captures; production temporal projection conditional on scheduling evidence'}
 out=protocol.parent/'overhead-summary.json'
 with out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps(r))
if __name__=='__main__':analyze(Path(sys.argv[1]))
