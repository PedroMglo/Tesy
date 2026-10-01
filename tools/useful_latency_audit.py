"""Offline no-model audit of the post-C198 receipts, pairs and complete raw manifests."""
import argparse,json,os,tempfile
from pathlib import Path
from native64_numeric import read
from c2_server_run import digest
from run_bounded import sha256
from native64_natural import require_freeze
from useful_latency_portfolio import analyze
from useful_latency_evaluate import evaluate


def publish(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.publish-',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
  os.link(tmp,path) # atomic, refuses an existing output; no retrospective replacement
 finally:os.unlink(tmp)


def raw_manifest(root):
 out={}
 for p in sorted((root/'raw').rglob('*')):
  if p.is_symlink():raise ValueError('unexpected raw symlink: '+str(p))
  if p.is_file():out[str(p.relative_to(root/'raw'))]={'bytes':p.stat().st_size,'sha256':sha256(p)}
 return {'raw_root':str((root/'raw').resolve()),'files':out,'total_bytes':sum(v['bytes'] for v in out.values()),'includes_invalid_and_partial':True}


def audit(root):
 require_freeze(root);family=read(root/'protocol.json');rows=[];summary=[]
 for rid,profile in family['order']:
  receipt=root/(rid+'-receipt.json')
  if not receipt.exists():summary.append({'run_id':rid,'profile':profile,'status':'NOT_RUN_AFTER_FAMILY_STOP','metrics':'NOT_RUN'});continue
  rc=read(receipt);raw=read(root/'raw'/(rid+'.json'));p=read(root/'protocols'/(rid+'.json'));c=read(root/(rid+'-config.json'))
  runtime=raw['preflight']['actually_loaded_parallel_runtime']
  if runtime['libraries_sha256']!=p['parallel_runtime']['libraries_sha256'] or runtime['initial_process_environment']!=p['parallel_runtime']['environment']:raise ValueError('recorded parallel identity changed')
  if rc['status']=='PASS_NATURAL_ARM':
   a=analyze(root,rid,profile,p,c)
   if a!=rc['row']:raise ValueError('row not reproducible '+rid)
   rows.append(a)
  token_ids=read(root/'raw'/(rid+'.tokenization.json'));requests=[]
  for item in raw['results']:
   t=item['timings'];s=item['stream_metrics'];validation=item.get('functional_validation');deadline=c['per_task_request_policy'][item['id']]['per_request_timeout_s']
   requests.append({'id':item['id'],'official_ids_n':len(token_ids[item['id']]),'official_ids_sha256':digest(token_ids[item['id']]),'tokenization_file_sha256':sha256(root/'raw'/(rid+'.tokenization.json')),
    'cache_n':t['cache_n'],'prompt_n':t['prompt_n'],'outputs_reported':item['usage']['completion_tokens'],'output_ids':'NOT_EXPOSED',
    'finish_reason':item['finish_reason'],'accepted':item['accepted'],'invalid_reason':item['invalid_reason'],
    'prefill_s':t['prompt_ms']/1000,'decode_s':t['predicted_ms']/1000,'native_predicted_n':t['predicted_n'],
    'first_reasoning_s':s['first_reasoning_chunk_s'],'first_final_s':s['first_final_content_chunk_s'],
    'completion_s':item['ended_s']-item['started_s'],
    'validated_s':validation['validated_monotonic_s']-(item['deadline_monotonic']-deadline) if validation and 'validated_monotonic_s' in validation else None,
    'validator_s':validation.get('validator_s') if validation else None,'final':item['message']['content'],'reasoning':item['message'].get('reasoning_content'),'functional':validation or 'NOT_VALIDATED'})
  summary.append({'run_id':rid,'profile':profile,'status':rc['status'],'reason':rc['reason'],'measurement_head':rc['measurement_head'],'requests':requests,'stop_reasons':raw['stop_reasons'],'maxima':(rc.get('row') or {}).get('maxima'),'cgroup_end':raw['cgroup_end']})
 result=None
 if len(rows)==len(family['order']):
  pairs=[(rows[0],rows[1]),(rows[3],rows[2])]+([(rows[4],rows[5])] if family['confirmation'] else [])
  result=evaluate(pairs,family['hypothesis'],family['confirmation'])
  if result!=read(root/'paired-metrics.json'):raise ValueError('paired decision not reproducible')
 return {'status':'REPRODUZIDO_MODEL_FREE_RECEIPT_AUDIT','hypothesis':family['hypothesis'],'all_planned_arms':summary,'paired_result':result or 'NOT_COMPUTABLE_INCOMPLETE_FAMILY','raw_manifest':raw_manifest(root)}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args();publish(a.output,audit(a.root.resolve()))
