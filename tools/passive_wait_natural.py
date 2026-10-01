"""Small post-C209 adapter over existing C2 + guarded native-family lifecycle."""
import argparse,json,math,time,copy
from pathlib import Path
import useful_latency_portfolio as old
import native64_natural as runner
from native64_numeric import read,save,git
from run_bounded import sha256
from c9_server_admission import validate_receipt
from c85_request_markers import validate as validate_markers
from c2_gate import GateError
from passive_wait_utility import *
SOURCES=tuple(dict.fromkeys(old.SOURCES+('tools/passive_wait_natural.py','tools/passive_wait_utility.py')))

def workload():
 w=old.supplied_workload();sql_response=read(old.PRIOR/'raw/c196-1-A32.json')['results'][2]['message']['content']
 history=w['tasks'][2][1]['messages']+[{'role':'assistant','content':sql_response}]
 w['holdout_task']=[JSON_ID,{'id':JSON_ID,'category':'independent-json-pipeline','messages':history+[{'role':'user','content':JSON_PROMPT}],'cache_prompt':True,'chat_template_kwargs':{'tesy_template_date':'2026-09-30'}}]
 w['holdout_fixtures']={'input':JSON_DATA,'expected':JSON_EXPECTED,'oracle':'independentPython max(versao,ingest), then filter cancellations, missing/null0, sortASCII'}
 w.pop('holdout_expected');w['scope']='fixed supplied C196 transcript, new responses never fed back'
 return w

def freeze(root,epoch,confirmation=False):
 root=root.resolve();root.mkdir();(root/'protocols').mkdir();(root/'raw').mkdir()
 for n in ('snapshot.json','resource-policy.json'):save(root/n,read(epoch/n))
 save(root/'session-input.json',read(old.PRIOR/'session-input.json'));save(root/'workload.json',workload())
 order='ABBAAB' if confirmation else 'ABBA';maximum=3600 if confirmation else 1680
 p={'schema':'post-c209-passive-wait-utility-v1','epoch':str(epoch.resolve()),'hypothesis':'H2','confirmation':confirmation,'cap_bytes':18*2**30,'order':[(root.name.split('-')[0]+f'-{i+1}-{v}',v) for i,v in enumerate(order)],'maximum_live_s':maximum,'arm_maximum_s':600 if confirmation else 420,'unit_runtime_max_s':595 if confirmation else 415,'remaining_reserved_live_s':600 if confirmation else 4200,'remaining_reserved_raw_bytes':256*2**20,'source_sha256':{k:sha256(runner.base.REPO/k) for k in SOURCES},'workload_sha256':sha256(root/'workload.json'),'claim':'Penalized utility + observed timing; no equal-FLOPs or generated-ID claim','deadline_s':[120,60,120]+([180] if confirmation else []),'validator_budget_s':2,'gate':{'SQL_gain_percent':8,'JSON_gain_percent':5,'U_gain_percent':5,'all_gains_positive':True,'protection_median':-5,'protection_pair':-15},'no_retry':True,'publication':'LOCAL_ONLY'}
 save(root/'protocol.json',p)
 for rid,profile in p['order']:
  pp,c=old.make(root,rid,profile,'H2',confirmation)
  names=list(old.IDS)+([JSON_ID] if confirmation else [])
  c.update(task_ids=names,total_timeout_s=525 if confirmation else 345,require_natural_stop=True,prospective_task_outcomes=True,per_task_request_policy={k:{'max_tokens':256 if i<2 else (384 if i==2 else 512),'per_request_timeout_s':p['deadline_s'][i]} for i,k in enumerate(names)},prompt_token_ranges={k:[1900,6500] for k in names})
  pp['expected_request_ids']=names;pp['portfolio']['source_sha256']=p['source_sha256'];pp['identity']['config_sha256']=runner.server.digest(c)
  save(root/'protocols'/(rid+'.json'),pp);save(root/(rid+'-config.json'),c)
 save(root/'freeze-manifest.json',{'sha256':{str(f.relative_to(root)):sha256(f) for f in root.rglob('*.json')},'created_at':runner.now(),'no_hash_of_own_commit':True})

def tasks(root):
 w=read(root/'workload.json');return w['tasks']+([w['holdout_task']] if read(root/'protocol.json')['confirmation'] else [])

def analyze(root,rid,profile,p,c):
 raw=read(root/'raw'/(rid+'.json'));ids=read(root/'raw'/(rid+'.tokenization.json'));names=p['expected_request_ids']
 samples=[json.loads(x) for x in (root/'raw'/(rid+'.samples.jsonl')).read_text().splitlines()]
 censor=None
 if raw['stop_reasons']:
  censor=censor_record(root,rid)
  raw=copy.deepcopy(raw);raw['returncode']=0;raw['stop_reasons']=[]
 # Shared authority checks transport, real child ownership, all resource guards and source hashes.
 maxima=validate_receipt(p,c,raw,samples,root,run_id=rid,protocol_filename='protocols/'+rid+'.json',expected_results=len(raw['results']))
 if censor is None:validate_markers(root/'raw'/(rid+'.request-markers.jsonl'),rid,names,raw['results'])
 if raw['preflight']['ready_elapsed_s']>30 or not raw['preflight'].get('actually_loaded_parallel_runtime'):raise GateError('runtime/readiness invalid')
 row={'run_id':rid,'profile':profile,'measurement_valid':True,'input_ids':ids,'nominal153':False,'requests':[],'maxima':maxima}
 for i,item in enumerate(raw['results']):
  if censor is not None and item['id']==names[-1]:break
  k=item['id'];t=item['timings'];sm=item['stream_metrics'];v=item['functional_validation'];deadline=c['per_task_request_policy'][k]['per_request_timeout_s'];start=item['request_start_monotonic']
  if not item['measurement_valid'] or not sm['done_observed'] or item['finish_reason'] not in ('stop','length') or type(item['usage']['completion_tokens']) is not int or not 0<item['usage']['completion_tokens']<=c['per_task_request_policy'][k]['max_tokens'] or t['cache_n']+t['prompt_n']!=len(ids[k]) or item['usage']['prompt_tokens']!=len(ids[k]):raise GateError('measurement/accounting invalid')
  req={'id':k,'outcome':item['outcome'],'functional_success':item['functional_success'],'validated_s':v['validated_monotonic_s']-start,'validator_s':v['validator_duration_s'],'completion_s':item['completed_monotonic']-start,'first_final_s':sm['first_final_content_chunk_s'],'trajectory':{'message':item['message'],'finish_reason':item['finish_reason'],'output_n':item['usage']['completion_tokens'],'predicted_n':t['predicted_n']},'native_timings':t,'stream_metrics':sm,'usage':item['usage'],'output_ids':'NOT_EXPOSED'}
  req['L']=task_loss(req,deadline);row['requests'].append(req)
  prefix=('T2' if i==1 else 'SQL' if i==2 else 'JSON' if i==3 else 'cold')
  row[prefix+'_first_final_s']=req['first_final_s'];row[prefix+'_completion_s']=req['completion_s']
  if t['predicted_n']<=0 or t['predicted_ms']<=0:raise GateError('decode native counters invalid')
  row[prefix+'_seconds_per_output']=t['predicted_ms']/1000/t['predicted_n']
  if i==0:row['cold_prefill_s']=t['prompt_ms']/1000
  if i==1:row['incremental_prefill_s']=t['prompt_ms']/1000
  if i==2:row['SQL_L']=req['L'];row['SQL_validated_s']=req['validated_s'] if req['functional_success'] else None
  if i==3:row['JSON_L']=req['L'];row['U']=(row['SQL_L']+req['L'])/2
 if censor is not None:
  last=names[-1];idx=len(names)-1
  if len(row['requests'])!=idx:raise GateError('deadline before final task; incomplete')
  prefix='JSON' if idx==3 else 'SQL'
  row['requests'].append({'id':last,'outcome':'DEADLINE_CENSORED','functional_success':False,'L':1.0,'validated_s':None,'completion_s':None,'validator_s':None,'first_final_s':None,'trajectory':censor['partial_message'],'censor':censor,'output_ids':'NOT_EXPOSED'})
  row[prefix+'_L']=1.0;row[prefix+'_validated_s']=None;row[prefix+'_first_final_s']=None;row[prefix+'_seconds_per_output']=None
  if idx==3:row['U']=(row['SQL_L']+1)/2
 expected=read(root/'workload.json')['official_ids']
 if any(ids[k]!=expected[k] for k in old.IDS):raise GateError('INCONCLUSIVE_INPUT_OR_PREFIX')
 row['nominal153']=(len(ids[old.IDS[0]]),len(ids[old.IDS[1]]),raw['results'][1]['timings']['cache_n'],raw['results'][1]['timings']['prompt_n'])==(2043,2197,2044,153)
 return row

def censor_record(root,rid):
 raw=read(root/'raw'/(rid+'.json'));names=read(root/'protocols'/(rid+'.json'))['expected_request_ids'];last=names[-1]
 ep=root/'raw'/(rid+f'.request-{len(names)}.jsonl')
 evidence=[json.loads(v) for v in ep.read_text().splitlines()]
 out=terminal_censor_contract(raw,evidence,last);message={'content':'','reasoning_content':''}
 for rec in evidence:
  if rec.get('kind')!='SSE_FRAGMENT':continue
  for line in rec.get('fragment','').splitlines():
   if not line.startswith('data: '):continue
   text=line[6:].strip()
   if text=='[DONE]':continue
   value=json.loads(text)
   for choice in value.get('choices',[]):
    delta=choice.get('delta',{})
    for k in message:
     if delta.get(k):message[k]+=delta[k]
 out['partial_message']=message
 markers=[json.loads(v) for v in (root/'raw'/(rid+'.request-markers.jsonl')).read_text().splitlines()]
 if not any(m['request_id']==last and m['kind']=='REQUEST_START' for m in markers):raise GateError('censor launch marker absent')
 if [r['id'] for r in raw['results'][:len(names)-1]]!=names[:-1]:raise GateError('censor incomplete preceding tasks')
 return out

def terminal_censor_allowed(root,rid):
 try:censor_record(root,rid);return True
 except (GateError,KeyError,ValueError,OSError):return False

def hooks(root):
 p=read(root/'protocol.json');return {'cap':18*2**30,'suite':'passivewaitutility','tasks':tasks,'checker':checker,'analyze':analyze,'arm_script':'tools/passive_wait_natural.py','evaluate':lambda pairs:evaluate(pairs,p['confirmation']),'accept_terminal_censor':terminal_censor_allowed}
if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('mode',choices=('freeze','arm','family'));q.add_argument('root',type=Path);q.add_argument('--epoch',type=Path);q.add_argument('--confirmation',action='store_true');q.add_argument('--run-id');q.add_argument('--measurement-head');a=q.parse_args()
 if a.mode=='freeze':freeze(a.root,a.epoch,a.confirmation)
 elif a.mode=='arm':raise SystemExit(runner.arm(a.root,a.run_id,a.measurement_head,hooks=hooks(a.root.resolve())))
 else:raise SystemExit(runner.family(a.root,hooks=hooks(a.root.resolve())))
