"""Thin post-C198 profiles/tasks over the existing guarded natural-family lifecycle."""
import argparse,json,os,re,time
from pathlib import Path
import native64_natural as runner
from native64_numeric import read,save,git,BACKEND
from run_bounded import sha256
from parallel_runtime import parallel_environment
from portfolio_workload import HOLDOUT_PROMPT,HOLDOUT_FIXTURES,holdout_expected,grade_holdout,JSON_TURNS
from useful_latency_evaluate import evaluate
from epoch_accounting import Epoch,now
from c9_server_admission import validate_receipt
from c85_request_markers import validate as validate_markers

IDS=runner.IDS
HOLDOUT='portfolio-holdout'
SOURCES=tuple(dict.fromkeys(runner.SOURCES+('tools/useful_latency_portfolio.py','tools/parallel_runtime.py','tools/portfolio_workload.py','tools/useful_latency_evaluate.py','tools/run_bounded.py')))
PRIOR=runner.base.REPO/'results/c196-native64-natural-screen-20260930T223734Z'

def supplied_workload():
 old=runner.tasks(PRIOR);raw=read(PRIOR/'raw/c196-1-A32.json');token_ids=read(PRIOR/'raw/c196-1-A32.tokenization.json')
 history=[];out=[]
 for (rid,task),result in zip(old,raw['results']):
  history+=task['messages'];task=dict(task,messages=list(history));out.append((rid,task))
  history+=[{'role':'assistant','content':result['message']['content']}]
 if [x['message']['content'].strip() for x in raw['results'][:2]]!=['48327','48327']:raise ValueError('published transcript changed')
 if [len(token_ids[k]) for k in IDS]!=[2043,2197,2292]:raise ValueError('published official inputs unavailable')
 hold={'id':HOLDOUT,'category':'fresh-independent-functional-holdout','messages':history+[{'role':'user','content':HOLDOUT_PROMPT}],
       'cache_prompt':True,'chat_template_kwargs':{'tesy_template_date':'2026-09-30'}}
 return {'schema':'post-c198-fixed-supplied-transcript-v1','tasks':out,'holdout_task':[HOLDOUT,hold],
   'official_ids':token_ids,'historical_raw_sha256':sha256(PRIOR/'raw/c196-1-A32.json'),
   'history':'Published final content supplied identically; new model answers do not change subsequent prompts',
   'known_sql':read(PRIOR/'workload.json'),'holdout_fixtures':HOLDOUT_FIXTURES,
   'holdout_expected':[holdout_expected(f) for f in HOLDOUT_FIXTURES],'qualification_json_turns':JSON_TURNS,
   'output_ids':'NOT_EXPOSED; never retokenized as native generation'}

def tasks(root):
 w=read(root/'workload.json');out=w['tasks']
 return out+[w['holdout_task']] if read(root/'protocol.json')['confirmation'] else out

def checker():
 def check(rid,item):
  text=item['message']['content'].strip()
  if rid==IDS[0]:
   if not re.fullmatch('[0-9]{5}',text):raise ValueError('CONTENT_T1_INVALID')
   return {'PASS':True,'scope':'five ASCII digits'}
  if rid==IDS[1]:
   if text!='48327':raise ValueError('CONTENT_T2_SUPPLIED_HISTORY_INVALID')
   return {'PASS':True,'scope':'exact supplied prior answer48327'}
  out=grade_holdout(text) if rid==HOLDOUT else runner.grade(text)
  out['validated_monotonic_s']=time.monotonic();return out
 return check

def make(root,rid,profile,hypothesis,confirmation,*,cap_bytes=None):
 cap=(20 if hypothesis=='H1' else 18)*2**30 if cap_bytes is None else cap_bytes
 runner.base.CAP=cap
 runner.base.BACKENDS={k:(BACKEND,'build-c75-cuda','27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5',{'TESY_CPU_WAVE_SKIP_PARKED':'1'}) for k in ('control','candidate')}
 runner.base.input_row=lambda unused:read(root/'session-input.json')
 p,c=runner.base.make(root,'control' if profile=='A' else 'candidate')
 cmd=c['server_command'];cmd[cmd.index('--moe-stream-cache')+1]='44s' if hypothesis=='H1' and profile=='B' else '40s'
 assert cmd[cmd.index('-ub')+1]=='32'
 names=list(IDS)+([HOLDOUT] if confirmation else [])
 if hypothesis=='H2' and profile=='B':c['explicit_env']['GOMP_SPINCOUNT']='0'
 c.update(suite='usefullatency',task_ids=names,total_timeout_s=410 if confirmation else 230,readiness_timeout_s=30,
   require_natural_stop=True,append_previous_assistant_to_next=False,
   per_task_request_policy={k:{'max_tokens':256 if i<2 else 384,'per_request_timeout_s':(180,90,120,180)[i]} for i,k in enumerate(names)},
   prompt_token_ranges={k:[1900,6000] for k in names},expected_official_token_ids=read(root/'workload.json')['official_ids'])
 c['request_policy']['per_request_timeout_s']=180
 prior=p.pop('c97');p.update(schema_version='useful-latency-portfolio-v1',protocol_id=rid+'-v1',expected_request_ids=names,
   execution_scope_unit=runner.unit(rid),optional_cpu_telemetry=True,
   parallel_runtime={'schema':'parallel-runtime-v1','environment':parallel_environment(dict(os.environ,**c['explicit_env'])),
                     'libraries_sha256':{str(Path('/lib64/libgomp.so.1').resolve()):sha256(Path('/lib64/libgomp.so.1').resolve())}})
 p['portfolio']={'profile':profile,'hypothesis':hypothesis,'run_id':rid,'model_stat':prior['model_stat'],'backend_tree':prior['backend_tree'],
   'source_sha256':{k:sha256(runner.base.REPO/k) for k in SOURCES},'workload_sha256':sha256(root/'workload.json')}
 p['identity']['config_sha256']=runner.server.digest(c)
 p['start_inventory']={'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(root/'resource-policy.json')}
 runner.validate_resource_protocol(p);return p,c

def freeze(root,epoch,hypothesis,confirmation=False):
 root=root.resolve();root.mkdir(parents=True,exist_ok=False);(root/'protocols').mkdir();(root/'raw').mkdir()
 for name in ('snapshot.json','resource-policy.json'):save(root/name,read(epoch/name))
 data=read(PRIOR/'session-input.json');data['template_date']='2026-09-30';save(root/'session-input.json',data)
 save(root/'workload.json',supplied_workload())
 order=('A','B','B','A','A','B') if confirmation else ('A','B','B','A')
 maximum=2880 if confirmation else 1200
 p={'schema':'post-c198-useful-latency-family-v1','epoch':str(epoch.resolve()),'hypothesis':hypothesis,'confirmation':confirmation,
   'cap_bytes':(20 if hypothesis=='H1' else 18)*2**30,'order':[(root.name.split('-')[0]+'-'+str(i+1)+'-'+v,v) for i,v in enumerate(order)],
   'maximum_live_s':maximum,'arm_maximum_s':480 if confirmation else 300,'unit_runtime_max_s':475 if confirmation else 295,
   'remaining_reserved_live_s':600 if confirmation else 3480,'remaining_reserved_raw_bytes':256*2**20,
   'source_sha256':{k:sha256(runner.base.REPO/k) for k in SOURCES},'workload_sha256':sha256(root/'workload.json'),
   'claim':'Identical supplied transcript; free outputs, no equal-compute claim',
   'S_gate':{'SQL_median_percent':8,'SQL_all_positive':True,'protection_median_min_percent':-5,'individual_min_percent':-15},
   'C_gate':{'SQL_median_percent':8,'holdout_median_percent':5,'all_primary_gains_positive':True},
   'no_retry':True,'publication':'LOCAL_ONLY'}
 save(root/'protocol.json',p)
 for rid,profile in p['order']:
  a,b=make(root,rid,profile,hypothesis,confirmation);save(root/'protocols'/(rid+'.json'),a);save(root/(rid+'-config.json'),b)
 save(root/'freeze-manifest.json',{'sha256':{str(k.relative_to(root)):sha256(k) for k in root.rglob('*.json')},'created_at':now(),'no_hash_of_own_commit':True})

def analyze(root,rid,profile,p,c):
 raw=read(root/'raw'/(rid+'.json'));ids=read(root/'raw'/(rid+'.tokenization.json'));names=p['expected_request_ids']
 samples=[json.loads(v) for v in (root/'raw'/(rid+'.samples.jsonl')).read_text().splitlines()]
 maxima=validate_receipt(p,c,raw,samples,root,run_id=rid,protocol_filename='protocols/'+rid+'.json',expected_results=len(names))
 if raw['preflight']['ready_elapsed_s']>30 or not raw['preflight'].get('actually_loaded_parallel_runtime'):raise ValueError('readiness/runtime identity missing')
 validate_markers(root/'raw'/(rid+'.request-markers.jsonl'),rid,names,raw['results'])
 reports=[];trajectory=[]
 for item in raw['results']:
  k=item['id'];t=item['timings'];sm=item['stream_metrics'];cap=c['per_task_request_policy'][k]['max_tokens']
  if not item['accepted'] or item['finish_reason']!='stop' or not sm['done_observed'] or not 0<item['usage']['completion_tokens']<cap:raise ValueError('non-natural/incomplete response')
  if item['usage']['prompt_tokens']!=len(ids[k]) or t['cache_n']+t['prompt_n']!=len(ids[k]) or not item.get('functional_validation',{}).get('PASS'):raise ValueError('accounting/functional incomplete')
  reports.append({'id':k,'input_ids':ids[k],'output_ids':'NOT_EXPOSED','message':item['message'],'usage':item['usage'],
    'timings':t,'stream_metrics':sm,'finish_reason':item['finish_reason'],'request_wall_s':item['ended_s']-item['started_s'],
    'functional_validation':item['functional_validation']})
  trajectory.append({'message':item['message'],'output_n':item['usage']['completion_tokens'],'predicted_n':t['predicted_n'],'finish_reason':item['finish_reason']})
 if [len(ids[k]) for k in IDS]!=[2043,2197,2292] or (raw['results'][1]['timings']['cache_n'],raw['results'][1]['timings']['prompt_n'])!=(2044,153):raise ValueError('INCONCLUSIVE_INPUT_OR_PREFIX')
 for k in IDS:
  if ids[k]!=read(root/'workload.json')['official_ids'][k]:raise ValueError('official input identity changed')
 a,b,sql=raw['results'][:3];ff=lambda x:x['stream_metrics']['first_final_content_chunk_s']
 row={'profile':profile,'run_id':rid,'valid':True,'nominal153':True,'input_ids':ids,'trajectory':trajectory,'requests':reports,'maxima':maxima,
   'T2_first_final_s':ff(b),'T2_completion_s':b['ended_s']-b['started_s'],'SQL_first_final_s':ff(sql),
   'SQL_validated_s':sql['functional_validation']['validated_monotonic_s']-(sql['deadline_monotonic']-120),
   'cold_prefill_s':a['timings']['prompt_ms']/1000,'cold_first_final_s':ff(a),'incremental_prefill_s':b['timings']['prompt_ms']/1000,
   'T2_seconds_per_output':b['timings']['predicted_ms']/1000/b['timings']['predicted_n'],
   'SQL_seconds_per_output':sql['timings']['predicted_ms']/1000/sql['timings']['predicted_n']}
 if len(names)==4:
  h=raw['results'][3];row.update(holdout_validated_s=h['functional_validation']['validated_monotonic_s']-(h['deadline_monotonic']-180),
    holdout_first_final_s=ff(h),holdout_seconds_per_output=h['timings']['predicted_ms']/1000/h['timings']['predicted_n'])
 return row

def hooks(root):
 p=read(root/'protocol.json')
 return {'cap':p['cap_bytes'],'suite':'usefullatency','tasks':tasks,'checker':checker,'analyze':analyze,
   'arm_script':'tools/useful_latency_portfolio.py','evaluate':lambda pairs:evaluate(pairs,p['hypothesis'],p['confirmation'])}

if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('mode',choices=('freeze','arm','family'));q.add_argument('root',type=Path)
 q.add_argument('--epoch',type=Path);q.add_argument('--hypothesis',choices=('H1','H2'));q.add_argument('--confirmation',action='store_true');q.add_argument('--run-id');q.add_argument('--measurement-head')
 args=q.parse_args()
 if args.mode=='freeze':freeze(args.root,args.epoch,args.hypothesis,args.confirmation)
 elif args.mode=='arm':raise SystemExit(runner.arm(args.root,args.run_id,args.measurement_head,hooks=hooks(args.root.resolve())))
 else:raise SystemExit(runner.family(args.root,hooks=hooks(args.root.resolve())))
