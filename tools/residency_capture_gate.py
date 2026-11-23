"""Fixed probe call-plan, numerical witnesses and logical capture qualification."""
import csv,hashlib,json,os,re,sys
from pathlib import Path
from c152_snapshot_read import snapshot,routes
from c152_journal_validate import validate

CORE={'attn_post_norm','ffn_moe_logits','ffn_moe_probs','ffn_moe_topk','ffn_moe_weights_softmax','ffn_moe_out'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def journal_window(path,initial):
 path=Path(path)
 if not 0<path.stat().st_size<=64*1024*1024:raise ValueError('journal size')
 lines=path.read_text().splitlines();at=next(i for i,x in enumerate(lines) if x.startswith('kind\t'))
 if path.name.endswith('.partial') or lines[0]!='#c156-expert-snapshot-v2':raise ValueError('incomplete journal window input')
 rows=lines[at+1:-1];cut=initial['transition_seq'];total=len(rows)
 if not 0<=cut<total or lines[-1]!=f'#end\t{total}\t0':raise ValueError('journal window/footer')
 for i,line in enumerate(rows):
  if int(line.split('\t')[1])!=i:raise ValueError('journal publication sequence')
 metadata=[x for x in lines[1:at] if not x.startswith('R\t')];previous=0;previous_request=0;windows=[]
 for x in lines[1:at]:
  if x.startswith('R\t'):
   _,req,a,b=x.split('\t');req,a,b=int(req),int(a),int(b)
   if req<=previous_request or a!=previous or b<a:raise ValueError('original request ranges')
   previous,previous_request=b,req
   if b>cut:windows.append(f'R\t{req}\t{max(a,cut)}\t{b}')
 if previous!=total:raise ValueError('original request coverage')
 out=Path(str(path)+'.window.trace');tmp=Path(str(out)+'.partial')
 with tmp.open('x') as f:f.write('\n'.join([lines[0],*metadata,*windows,lines[at],*rows[cut:],lines[-1]])+'\n');f.flush();os.fsync(f.fileno())
 os.link(tmp,out);tmp.unlink()
 return out
def plan(root):
 with (root/'calls.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
 expected=[(i+1,1,'prefix-warmup',256*i,min(2043,256*i+255)) for i in range(8)]+[(9,2,'warm-prefill',2044,2048),(10,2,'warm-prefill',2049,2196)]+[(11+i,2,'decode',2197+i,2197+i) for i in range(47)]
 if len(rows)!=57:raise ValueError('call count')
 end=None
 for row,want in zip(rows,expected):
  actual=tuple(int(row[k]) if k!='phase' else row[k] for k in ('call','request','phase','first','last'))
  if actual!=want or int(row['n_tokens'])!=want[4]-want[3]+1:raise ValueError('fixed call plan')
  a,b=int(row['begin_us']),int(row['end_us'])
  if b<a or end is not None and a<end:raise ValueError('call order')
  end=b
 if (root/'full-logits.f32').stat().st_size!=57*201088*4:raise ValueError('complete full logits')
 return rows

def witnesses(root):
 seen={};coverage=set();active=set()
 for row in csv.reader((root/'witness/index.tsv').read_text().splitlines(),delimiter='\t'):
  if len(row)!=3:raise ValueError('witness index')
  name,size,shape=row;match=re.fullmatch(r'(9|10|11|57)-(\d+)-(.+)-(\d+)\.bin',name)
  if not match or name in seen:raise ValueError('witness identity')
  call,layer,stage,occ=match.groups();shape=list(map(int,shape.split(',')))
  if not 0<=int(layer)<36 or stage not in CORE or len(shape)!=4 or any(x<0 for x in shape):raise ValueError('witness shape/layer')
  width=4 if stage=='ffn_moe_topk' else 128 if stage in ('ffn_moe_logits','ffn_moe_probs') else 2880
  if stage=='ffn_moe_weights_softmax':
   if shape[0]!=1 or shape[1]!=4 or shape[3]!=1:raise ValueError('routing weight shape')
  elif shape[0]!=width or shape[2:]!=[1,1]:raise ValueError('active state shape')
  n=4
  for x in shape:n*=x
  p=root/'witness'/name
  if p.stat().st_size!=int(size) or n!=int(size):raise ValueError('witness bytes')
  seen[name]={'sha256':sha(p),'shape':shape,'bytes':int(size)};coverage.add((int(call),int(layer),stage))
  if int(size)>0:active.add((int(call),int(layer),stage))
 if coverage!={(c,l,s) for c in (9,10,11,57) for l in range(36) for s in CORE}:raise ValueError('incomplete active witness coverage')
 if active!=coverage:raise ValueError('active states missing')
 return seen

def capture(root,trace,route_path,hashes):
 callplan=plan(root);r=routes(route_path)
 snaps=[snapshot(root/name,expected_hashes=hashes) for name in ('before-warm.snap','after-prefill.snap','final.snap')]
 window=journal_window(trace,snaps[0]);j=validate(window,initial=snaps[0])
 if set(j['calls'])!=set(range(9,58)):raise ValueError('journal call ids')
 for call,expected in zip(range(9,58),callplan[8:]):
  pair=j['calls'][call]
  # Journal CALL has ggml-time boundaries inside the fenced probe interval.
  a,b=pair['begin'],pair['end']
  if not int(expected['begin_us'])<=a['mono_us']<=b['mono_us']<=int(expected['end_us']):raise ValueError('journal/probe call containment')
 if [(x['request'],x['sequence'],x['phase'],x['call_id']) for x in snaps]!=[(2,0,0,8),(2,1,1,10),(2,2,2,57)]:raise ValueError('snapshot markers')
 with (root/'snapshots.tsv').open() as f:timing=list(csv.DictReader(f,delimiter='\t'))
 if len(timing)!=3:raise ValueError('snapshot timing count')
 for row,x in zip(timing,snaps):
  if not int(row['begin_us'])<=x['mono_us']<=int(row['end_us']) or int(row['bytes'])!=(root/row['name']).stat().st_size:raise ValueError('snapshot logical cut interval')
 dec=[x for x in r if x['call_id']>=11]
 if len(dec)!=47*36 or any(x['request']!=2 or x['mode']!=0 or len(x['ids'])!=4 for x in dec):raise ValueError('decode route cardinality')
 for call in range(11,58):
  if [x['layer'] for x in dec if x['call_id']==call]!=list(range(36)):raise ValueError('decode route layer ordering')
 return {'status':'LOGICAL_CAPTURE_VALIDATED','original_trace_sha256':sha(trace),'validated_window_sha256':sha(window),'logical_window_start_seq':snaps[0]['transition_seq'],'events':len(j['rows']),'loads':len(j['loads']),'decode_demands':len(dec)*4,'snapshot_bytes':sum((root/x['name']).stat().st_size for x in timing),'snapshot_lock_copy_and_write_us':sum(int(x['end_us'])-int(x['begin_us']) for x in timing),'scope':'57-call direct C API schedule; accepted journal calls9..57 seeded by actual before-warm snapshot. Prefix logs bounded/discarded before publication; original raw and any pre-cut tail preserved. 47 teacher-forced forwards, not C142 46 decode evaluations or server warm state'}

def numeric(off,on):
 a=plan(off);b=plan(on);x=witnesses(off);y=witnesses(on)
 if x!=y or sha(off/'full-logits.f32')!=sha(on/'full-logits.f32'):raise ValueError('same-profile warm state/logit mismatch')
 return {'status':'WARM_SELECTED_STATES_AND_ALL_LOGITS_BITWISE_PASS','selected_witness_files':len(x),'full_logits':57,'scope':'Warm shape selected states, routers/weights and full logits; numerical observer overhead excluded from timing qualification'}
if __name__=='__main__':
 p=json.loads(Path(sys.argv[1]).read_text());d=Path(sys.argv[1]).parent;off=Path(p['runs'][0]['command'][-1]);on=Path(p['runs'][1]['command'][-1]);e=p['runs'][1]['env'];hashes=[e['TESY_C152_'+x+'_HASH'] for x in ('MODEL','SOURCE','BUILD','PROFILE')]
 result={'numeric':numeric(off,on),'capture':capture(on,Path(e['TESY_C84_EXPERT_TRACE_FILE']),Path(e['TESY_C152_ROUTE_FILE']),hashes)}
 with (d/'numeric-summary.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result))
