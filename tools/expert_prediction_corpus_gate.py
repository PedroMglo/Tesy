"""Original-router auxiliary corpus; no functional-success or latency score."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np

def inspect(root,fixture,case,reference=False,expected=None):
 root=Path(root);v=json.loads((root/'result.json').read_text());n=v.get('decode_calls');ids=v.get('input_ids')
 if type(n) is not int or not 0<=n<=(32 if reference else 128):raise ValueError('actual bounded forward count')
 if ids!=fixture['ids'] or not 1800<=len(ids)<=2600 or any(type(x) is not int or not 0<=x<201088 for x in ids):raise ValueError('official frozen input IDs')
 if v.get('schema')!='task-separated-original-R0-score-corpus-v1' or v.get('model_original') is not True or v.get('case')!=case or v.get('profile')!='R0' or v.get('mode')!=0 or v.get('source_horizon')!=2 or v.get('CPU_layers')!=[2,24] or v.get('CPU_backend_threads')!=8 or v.get('byte_forecasting') is not False or v.get('trained_weights') is not False or v.get('reference_supplied') is not reference or v.get('capture_cap')!=(32 if reference else 128):raise ValueError('capture numerical/auxiliary policy')
 if v.get('template_date')!='2026-09-30' or v.get('reasoning_effort')!='medium' or v.get('sampling_policy')!='native-greedy-temp0-seed42':raise ValueError('sampler/template')
 if any(v.get(k)!=n*23 for k in ('feature_rows','true_label_rows')):raise ValueError('missing actual feature/label rows')
 for k in ('prefix_s','capture_decode_s','original_native_feature_cost_us'):
  x=v.get(k)
  if type(x) not in (int,float) or not math.isfinite(x) or x<0 or (n>0 and x==0):raise ValueError('finite observed capture clock')
 tokens=v.get('consumed_native_ids');winners=v.get('native_argmax_ids')
 if type(tokens) is not list or len(tokens)!=n or type(winners) is not list or len(winners)!=n+1 or any(type(x) is not int or not 0<=x<201088 for x in tokens+winners):raise ValueError('native position mapping')
 if reference:
  if n!=32 or tokens!=fixture['continuation_ids']:raise ValueError('provided32reference IDs')
 elif tokens!=winners[:n]:raise ValueError('nativegreedy continuation mismatch')
 arrays={}
 for file in ('early-native-scores.f32','true-routing-scores.f32'):
  p=root/file
  if p.stat().st_size!=n*23*128*4:raise ValueError('corpus feature/label truncated')
  x=np.fromfile(p,dtype='<f4').reshape(n,23,128)
  if not np.isfinite(x).all():raise ValueError('nonfinite corpus scores')
  arrays[file]=x
 router=json.loads((root/'actual-router-ids.json').read_text())
 if type(router) is not list or len(router)!=n*23*4 or any(type(x) is not int or not 0<=x<128 for x in router):raise ValueError('authoritative router IDs absent')
 rank=np.sort(np.argsort(-arrays['true-routing-scores.f32'],kind='stable',axis=2)[:,:,:4],axis=2)
 if not np.array_equal(rank,np.array(router).reshape(n,23,4)):raise ValueError('native original label/authoritative top4 mismatch')
 p=root/'first33.logits.f32';rows=min(n+1,33)
 if p.stat().st_size!=rows*201088*4:raise ValueError('selected full logit rows truncated')
 logits=np.fromfile(p,dtype='<f4').reshape(rows,201088)
 if not np.isfinite(logits).all() or logits.argmax(axis=1).tolist()!=winners[:rows]:raise ValueError('finite full row/native argmax mismatch')
 h=hashlib.sha256(p.read_bytes()).hexdigest()
 if reference and (not expected or h!=expected):raise ValueError('selected R0 bitwise reference failed')
 return {'status':'PASS_ORIGINAL_ROUTER_CORPUS' if n else 'PARTIAL_EOS_NO_TRAINING_ROWS','case':case,'decode_calls':n,'layer_rows':23*n,'selected_full_logits_rows':rows,'selected_logits_sha256':h,'terminal_eog':v['terminal_eog'],'scope':'Auxiliary score-corpus originalR0, actualnativeprefix/labels. Not final functional quality or latency/confirmed-output-throughput claim.'}

def vocabulary(fixture,tasks):
 if len(tasks)!=8 or list(fixture)!=[t['id'] for t in tasks] or len(set(fixture))!=8:raise ValueError('exact8orderedunique training conversations')
 out=[]
 for t in tasks:
  v=fixture[t['id']];ids=v.get('ids');prompt=v.get('rendered_prompt')
  if type(ids) is not list or not 1800<=len(ids)<=2600 or any(type(i) is not int or not 0<=i<201088 for i in ids):raise ValueError('actual official corpus IDs')
  if v.get('task')!=t or t.get('capture_nonEOS_forward_cap')!=128 or v.get('weights_loaded') is not False or v.get('forwards')!=0 or v.get('template_date')!='2026-09-30' or v.get('reasoning_effort')!='medium' or type(prompt) is not str or '2026-09-30' not in prompt or 'Reasoning: medium' not in prompt:raise ValueError('vocabulary-only/task/date/medium identity')
  out.append({'case':t['id'],'official_input_count':len(ids),'prefix_count':len(ids)-153,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
 return {'status':'PASS_FROZEN_TRAINING_CORPUS_VOCABULARY','cases':out,'weights_loaded':False,'forwards':0}

def main():
 a=argparse.ArgumentParser();a.add_argument('root',type=Path);a.add_argument('--fixture',type=Path);a.add_argument('--case');a.add_argument('--tasks',type=Path);a.add_argument('--reference',action='store_true');a.add_argument('--expected');a.add_argument('--output',type=Path,required=True);p=a.parse_args();v=vocabulary(json.loads(p.root.read_text()),json.loads(p.tasks.read_text())) if p.tasks else inspect(p.root,json.loads(p.fixture.read_text())[p.case],p.case,p.reference,p.expected)
 with p.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
 print(v['status'])
if __name__=='__main__':main()
