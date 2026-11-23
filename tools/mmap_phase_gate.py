"""Pinned native32+4 diagnostic gates; historical189+32 contract unchanged."""
import csv,hashlib,json,math,struct,sys
from pathlib import Path
from c149_numeric_gate import payload,byte_entry
PHASES=('prefill0','decode0','decode1','decode2','decode3')
STAGES=('attn_post_norm','ffn_moe_logits','ffn_moe_probs','ffn_moe_topk','ffn_moe_weights_softmax','ffn_moe_out')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def logits(root):
 out={}
 for name in PHASES:
  p=root/(name+'.logits.f32');data=p.read_bytes()
  if len(data)!=201088*4 or any(not math.isfinite(x[0]) for x in struct.iter_unpack('<f',data)):raise ValueError('five complete finite logit rows')
  out[name]=sha(p)
 return out

def inspect(root,tensors,verification):
 seen=set();hashes={}
 if tuple((root/'phases.txt').read_text().splitlines())!=PHASES:raise ValueError('small diagnostic phase schedule')
 for row in csv.DictReader((root/'index.tsv').open(),delimiter='\t'):
  key=(row['phase'],int(row['layer']),row['name'])
  if key in seen or key[0] not in PHASES or not 0<=key[1]<36 or key[2] not in STAGES:raise ValueError('stage/identity/duplicate')
  seen.add(key);p=root/row['file']
  if p.parent!=root or p.name.endswith('.partial'):raise ValueError('payload path')
  adapter=dict(row)
  # SOFTMAX_WEIGHT aliases biased logits as probs; width/float rules identical.
  if adapter['name']=='ffn_moe_probs':adapter['name']='ffn_moe_logits_biased'
  payload(adapter,p.read_bytes());hashes[p.name]=sha(p)
 if seen!={(p,l,s) for p in PHASES for l in range(36) for s in STAGES}:raise ValueError('all36 selected state coverage')
 byte_keys=set()
 for row in csv.DictReader((root/'byte_checks.tsv').open(),delimiter='\t'):
  byte_entry(row,tensors);k=(int(row['layer']),int(row['component']),int(row['expert']))
  if k in byte_keys:raise ValueError('duplicate canonical byte check')
  byte_keys.add(k)
 if verification:
  if {(l,k) for l,k,e in byte_keys}!={(l,k) for l in range(36) for k in range(6)}:raise ValueError('all expert weight/bias components')
 elif byte_keys:raise ValueError('state mode unexpectedly verifies payloads')
 return {'payload_sha256':hashes,'logits_sha256':logits(root),'canonical_slices':len(byte_keys),'selected_payloads':len(seen),'scope':'32+4 native boundary, not189+32 or session/context8192 coverage'}
def compare_logits(first,second):
 if logits(first)!=logits(second):raise ValueError('observer same-profile full logit mismatch')
 return {'status':'FIVE_LOGIT_ROWS_BITWISE_PASS'}
def phases(root):
 rows=list(csv.DictReader((root/'phase-timing.tsv').open(),delimiter='\t'))
 if [x['phase'] for x in rows]!=['load-readiness',*PHASES]:raise ValueError('phase timings complete')
 prior=0
 for x in rows:
  a,b=int(x['begin_us']),int(x['end_us'])
  if a<prior or b<a or not 0<=int(x['verify_us'])<=int(x['callback_us'])<=b-a or not 0<=int(x['capture_us'])<=int(x['callback_us']):raise ValueError('nested phase interval')
  prior=b
 return rows
def reference_result(path,layer):
 rows=[json.loads(line) for line in Path(path).read_text().splitlines() if line.startswith('{')]
 if len(rows)!=1:raise ValueError('one complete native reference JSON required')
 result=rows[0]
 if result.get('schema')!='c149-upstream-cpu-expert-layer-reference-v1' or result.get('layer')!=layer or result.get('device')!='cpu' or result.get('canonical_layer_bytes')!=1697956352 or result.get('all_bitwise') is not True or result.get('numeric_rows')!=5 or result.get('masked_rows')!=0:raise ValueError('reference identity/coverage/bitwise')
 values=result.get('rows',[])
 if [r.get('phase') for r in values]!=list(PHASES):raise ValueError('reference phase coverage')
 for r in values:
  if r.get('state')!='NUMERIC' or r.get('tokens')!=(32 if r['phase']=='prefill0' else 1) or r.get('routing_ids_equal') is not True or r.get('routing_weights_bitwise') is not True or r.get('ffn_bitwise') is not True:raise ValueError('canonical reference row mismatch')
  for key in ('routing_weights_max_abs','routing_weights_rmse','routing_weights_nonfinite','ffn_max_abs','ffn_rmse','ffn_nonfinite'):
   if type(r.get(key)) not in (int,float) or not math.isfinite(r[key]) or r[key]!=0:raise ValueError('reference nonfinite/nonzero error')
 return result
if __name__=='__main__':
 if sys.argv[1]=='reference':print(json.dumps(reference_result(Path(sys.argv[2]),int(sys.argv[3]))));raise SystemExit(0)
 if sys.argv[1]=='reference-family':
  protocol=Path(sys.argv[2]);p=json.loads(protocol.read_text());runs=p['runs']
  if len(runs)!=36 or [r['command'][-3] for r in runs]!=[str(i) for i in range(36)]:raise ValueError('exact36 reference arms')
  results=[reference_result(protocol.parent/'raw'/(r['id']+'.stdout'),i) for i,r in enumerate(runs)]
  out={'status':'NATIVE32_PLUS4_CANONICAL36_FFN_BITWISE_PASS','layers':36,'numeric_rows':180,'scope':'Captured native32+4 selected FFN activations,original routing/biases/weights. Not whole-model attention/KV proof or189+32/prefix153/server qualification'}
  with (protocol.parent/'reference-summary.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
  print(json.dumps(out));raise SystemExit(0)
 if sys.argv[1]=='compare':print(json.dumps(compare_logits(Path(sys.argv[2]),Path(sys.argv[3]))));raise SystemExit(0)
 protocol=Path(sys.argv[1]);p=json.loads(protocol.read_text());runs=[r for r in p['runs'] if not r.get('model_free')];roots=[Path(r['command'][-2]) for r in runs];tensors={x['name']:x for x in map(json.loads,Path(p['tensor_metadata_path']).read_text().splitlines()) if 'name' in x}
 n,s,v=roots;compare_logits(n,s);compare_logits(n,v);a=inspect(s,tensors,False);b=inspect(v,tensors,True)
 if a['payload_sha256']!=b['payload_sha256']:raise ValueError('state/verify selected states mismatch')
 result={'status':'NATIVE32_PLUS4_OBSERVER_BITS_AND_PAYLOAD_PASS_CANONICAL_FFN_PENDING','numeric_states':180,'selected_payloads':1080,'full_logits':5,'canonical_slices':b['canonical_slices'],'phase_timing':{r['label']:phases(root) for r,root in zip(runs,roots)},'scope':'Small32+4 diagnostic only, no broad189+32/prefix153/server/quality/performance qualification. verify_us and capture_us are nested in callback_us, which is within forward; never sum these intervals','page_cache':'Initial census and retained within-family pages; foreign ownership may be unknown, no equal-memory performance claim','next_action':'36 canonical FFN references if remaining30min branch budget admits; then decide remaining prefix/full-shape gates'}
 with (protocol.parent/'phase-summary.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result))
