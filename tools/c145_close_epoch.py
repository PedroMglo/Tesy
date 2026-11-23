#!/usr/bin/env python3
"""Append-only continuation ledger anchored to C137; no model actions."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
def close(repo,out):
 results=repo/'results';base=results/'c137-slots44-numeric-20260929T2217Z/epoch-checkpoint.json';base_row=load(base)
 entries=[]
 # Host premodel admission units, no inference.
 for name,seconds,status in [('c139-slots44-numeric-20260929T2315Z',60,'NOT_ADMITTED_HOST_HEADROOM'),('c140-slots44-numeric-20260929T2324Z',60,'ADMITTED_E20')]:
  r=results/name;baseline=load(r/'snapshot.json')['baseline'][-1]['elapsed_s'];entries.append({'unit':name+'-inventory','physical_charge_upper_s':max(seconds,baseline)+120,'observed_baseline_s':baseline,'unrecorded_setup_queries_upper_estimate_s':120,'source':str((r/'snapshot.json').relative_to(repo)),'sha256':sha(r/'snapshot.json'),'status':status,'model_active_s':0,'class':'live without model'})
 r=results/'c140-slots44-numeric-20260929T2324Z';p=r/'unit-receipt.json';u=load(p)
 numerical=[]
 for f in sorted((r/'raw').glob('*.json')):
  row=load(f)
  if 'elapsed_s' in row and 'backend_sha' in row:numerical.append({'process':f.stem,'elapsed_s':row['elapsed_s'],'source':str(f.relative_to(repo)),'sha256':sha(f)})
 entries.append({'unit':'c140-numeric-and36references','started_utc':u['started_utc'],'ended_utc':u['ended_utc'],'physical_charge_upper_s':u['elapsed_s'],'source':str(p.relative_to(repo)),'sha256':sha(p),'status':u['status'],'model_active_s':'UNKNOWN exact compute-only; individual process elapsed includes init/waits','processes':numerical,'nested_scope_envelopes_counted_once':True})
 for name in ('c141-uniform44-screen-20260929T2330Z','c142-uniform44-confirm-20260929T2353Z'):
  r=results/name
  for p in sorted((r/'raw').glob('*.receipt.json')):
   if '.start-inventory.' in p.name:continue
   row=load(p);a,b=map(datetime.fromisoformat,(row['started_utc'],row['ended_utc']));elapsed=(b-a).total_seconds()
   raw=load(r/'raw'/f"{row['run_id']}.json")
   envelope=r/'raw'/f"{row['run_id']}.service-envelope.json"
   measured=load(envelope)['elapsed_s'] if envelope.exists() else None
   if measured is not None and measured>elapsed+15:raise RuntimeError('service envelope exceeded conservative per-arm allowance')
   entries.append({'unit':row['run_id'],'started_utc':row['started_utc'],'ended_utc':row['ended_utc'],'physical_charge_upper_s':elapsed+15,'receipt_elapsed_s':elapsed,'outside_receipt_upper_bound_s':15,'service_envelope_elapsed_measured_s':measured,'server_process_elapsed_s':raw['elapsed_s'],'request_active_measured_sum_s':sum(x['ended_s']-x['started_s'] for x in raw['results']),'request_model_reported_prefill_decode_sum_s':sum((x['timings']['prompt_ms']+x['timings']['predicted_ms'])/1000 for x in raw['results']),'class':'whole live unit including inventory; overlapping phases not added','status':row['status'],'source':str(p.relative_to(repo)),'sha256':sha(p),'raw_sha256':sha(r/'raw'/f"{row['run_id']}.json")})
 r=results/'c143-slots40-optin-20260930T0012Z';p=r/'live-smoke-receipt.json';u=load(p)
 entries.append({'unit':'c143-model-free-live-smoke','physical_charge_upper_s':u['physical_live_elapsed_s']+u.get('nonreceipt_setup_cleanup_upper_s',15),'model_active_s':0,'status':u['status'],'source':str(p.relative_to(repo)),'sha256':sha(p),'includes':u['includes']})
 # Snapshot/preset preparation, if performed, has separate60s live admission.
 p=r/'prepared-preset-receipt.json'
 if p.exists():
  u=load(p);entries.append({'unit':'c143-preset-prepare-live-inventory','physical_charge_upper_s':u['elapsed_s']+15,'model_active_s':0,'source':str(p.relative_to(repo)),'sha256':sha(p),'status':u['status']})
 raw_rows=[];seen=set();raw_total=0
 for r in sorted(results.iterdir()):
  m=re.match(r'c(\d+)',r.name)
  if not m or not 120<=int(m[1])<=143 or not (r/'raw').is_dir():continue
  files=[];size=0
  for p in sorted((r/'raw').rglob('*')):
   if not p.is_file():continue
   st=p.stat();key=(st.st_dev,st.st_ino)
   if key in seen:continue
   seen.add(key);size+=st.st_size;files.append((str(p.relative_to(r/'raw')),st.st_size,sha(p)))
  digest=hashlib.sha256(json.dumps(files,separators=(',',':')).encode()).hexdigest()
  raw_rows.append({'root':str((r/'raw').relative_to(repo)),'unique_files':len(files),'bytes':size,'name_size_sha256_tree':digest});raw_total+=size
 now=datetime.now(timezone.utc);deadline=datetime.fromisoformat('2026-09-30T01:31:15+00:00');epochstart=datetime.fromisoformat('2026-09-29T13:31:15+00:00')
 added=sum(x['physical_charge_upper_s'] for x in entries);charged=base_row['physical_charged_upper_estimate_s']+added
 prior=[]
 for p in sorted(results.glob('c*/epoch-checkpoint.json')):
  try:row=load(p)
  except Exception:continue
  if row.get('epoch_id')==base_row['epoch_id'] and p.parent.name<='c137-slots44-numeric-20260929T2217Z':prior.append({'source':str(p.relative_to(repo)),'sha256':sha(p),'physical_charged_upper_estimate_s':row.get('physical_charged_upper_estimate_s')})
 ledger={'schema':'c145-closed-continuation-ledger-v1','epoch_id':base_row['epoch_id'],'epoch_start_utc':epochstart.isoformat(),'deadline_utc':deadline.isoformat(),'closure_utc':now.isoformat(),'wall_elapsed_s':(now-epochstart).total_seconds(),'wall_remaining_s':(deadline-now).total_seconds(),'physical_accounting_authority':'ESTIMADO conservative process/service bounds, measured intervals retained separately; not exact active model time','physical_limit_s':28800,'prior_upper_bound_s':base_row['physical_charged_upper_estimate_s'],'prior_checkpoint':str(base.relative_to(repo)),'prior_checkpoint_sha256':sha(base),'prior_checkpoint_chain':prior,'continuation_units':entries,'new_physical_charge_upper_s':added,'physical_charged_upper_estimate_s':charged,'physical_remaining_lower_bound_s':28800-charged,'pause_resume':{'owner_pause_at_c137':'preserved NOT_RUN_OWNER_REQUESTED_PUBLICATION, pause included in wall','exact_resume_utc':'NOT_CAPTURED; no wall discount','first_durable_host_observation':load(results/'c139-slots44-numeric-20260929T2315Z/snapshot.json')['utc']},'accounting_errata':['C139/C140 published inventory charges60s covered baseline only; this ledger includes measured baseline plus120s conservative source-command envelope for unrecorded pre/post inventory queries (eight calls bounded15s each); not measured active model time. C139 inherited prior_checkpoint_sha256 points to C136 though values/method included C137; this ledger explicitly anchors actual C137 hash and charges C139 once. Original file preserved.','C141 receipt-only checkpoint retained; service-envelope checkpoint adds15s per arm; same upper bound applied to C142, independent actual service envelopes checked.'],'model_free_and_compile':'wall only; no blanket conversion to inference time','model_active_total_s':'UNKNOWN; request windows and numeric process times retained separately','failures_preserved':['C139 NOT_ADMITTED before model','C140 freeze-attempt0 FAIL_HARNESS_PREMODEL (overlaps same inventory, not double counted)','all prior FAIL/NO_GO/owner interruptions unchanged'],'raw_limit_bytes':20*2**30,'raw_unique_bytes':raw_total,'raw_remaining_bytes':20*2**30-raw_total,'raw_roots':raw_rows,'raw_method':'unique dev/inode under epoch-unit raw roots, logical bytes, includes all FAILs; sources/builds/weights excluded','publication':'LOCAL_ONLY','source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()}
 if charged>28800 or now>deadline or raw_total>20*2**30:raise RuntimeError('closure budget exceeded; preserve diagnostics before any more live work')
 save(out/'epoch-ledger.json',ledger)
 save(out/'raw-epoch-manifest.json',{'schema':'c145-raw-epoch-v1','tree_contract':'SHA256 canonical JSON list [relative_path,size,file_sha256] sorted per root; unique dev/inode','roots':raw_rows,'total_bytes':raw_total})
 return ledger
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=close(a.repo,a.output);print(json.dumps({k:d[k] for k in ('physical_charged_upper_estimate_s','physical_remaining_lower_bound_s','wall_remaining_s','raw_unique_bytes')}))
