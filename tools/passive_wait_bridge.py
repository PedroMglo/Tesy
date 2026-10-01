"""Bounded numeric bridge using the original C127 capture and existing monitor."""
import argparse,json,os,subprocess,threading,time
from pathlib import Path
from native64_numeric import read,save,git,BACKEND,IDS
from run_bounded import sha256,relevant_environment
from host_resource_policy import freeze_protocol_resource_limits
from parallel_runtime import parallel_environment,mapped_parallel_runtime
from epoch_accounting import Epoch,now
from c70_full_boundary_gate import inspect
from c9_server_admission import MODEL

CAP=18*2**30

def freeze(root,epoch):
 root=root.resolve();root.mkdir();(root/'raw').mkdir()
 old=read('results/c127-slots40-numeric-20260929T1654Z/protocol.json');lib=Path('/lib64/libgomp.so.1').resolve()
 if sha256(old['binary_path'])!=old['binary_sha256']:raise ValueError('C127 executable identity changed')
 policy=read(epoch/'resource-policy.json')
 save(root/'resource-policy.json',policy)
 save(root/'protocol.json',{'schema':'post-c198-passive-wait-numeric-v1','epoch':str(epoch.resolve()),'execution_scope_unit':'tesy-'+root.name.split('-')[0]+'-passive-wait-bridge',
   'resources':freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP),'limits':{},
   'start_inventory':{'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(root/'resource-policy.json')},
   'binary':old['binary_path'],'binary_sha256':old['binary_sha256'],'model_stat':old['model_stat'],'libraries':old['backend_libraries_sha256'],
   'parallel_library':{str(lib):sha256(lib)},'inputs':str(IDS),'input_sha256':sha256(IDS),'deadline_s':300,'capture_timeout_s':70,
   'raw_projection_bytes':256*2**20,'control_env':{'TESY_CPU_WAVE_SKIP_PARKED':'1'},'candidate_env':{'TESY_CPU_WAVE_SKIP_PARKED':'1','GOMP_SPINCOUNT':'0'},
   'numeric':'both waves ON, ub32 slots40: selected core/routers/weights, masks and five full logits bitwise/finite; canonical C127 refs reused',
   'source_sha256':sha256(__file__),'publication':'LOCAL_ONLY'})

def run(root):
 root=root.resolve();p=read(root/'protocol.json');ep=Epoch(p['epoch']);start=now();end=start['monotonic_s']+p.get('deadline_s',300);status='FAIL_NUMERIC_OR_RESOURCE';reason=None;rows=[]
 if git('status','--porcelain') or relevant_environment(os.environ):raise ValueError('unclean measurement/environment')
 if not ep.budget(p.get('deadline_s',300)+p.get('remaining_reserved_live_s',1200+2880+600),p.get('raw_projection_bytes',256*2**20)+256*2**20)['admitted']:raise ValueError('bridge plus remaining portfolio not admitted')
 if sha256(p['binary'])!=p['binary_sha256'] or sha256(IDS)!=p['input_sha256'] or any(sha256(BACKEND/k)!=v for k,v in p['libraries'].items()):raise ValueError('prelaunch numeric identity changed')
 measurement=git('rev-parse','HEAD')
 try:
  caps=[]
  for i,envkey in enumerate(('control_env','candidate_env')):
   rid=root.name.split('-')[0]+'-'+('A' if i==0 else 'B');env=p[envkey];stem=root/'raw'/rid;capture=Path(str(stem)+'.capture');envfull=dict(os.environ,**env)
   contract={'schema':'parallel-runtime-v1','environment':parallel_environment(envfull),'libraries_sha256':p['parallel_library']}
   runtime=[];errors=[];done=threading.Event()
   def observe():
    while not done.wait(.05):
     try:
      samples=Path(str(stem)+'.samples.jsonl')
      if not samples.exists():continue
      lines=samples.read_text().splitlines()
      if not lines:continue
      pid=json.loads(lines[-1])['pid'];runtime.append(mapped_parallel_runtime(pid,contract));return
     except (FileNotFoundError,ProcessLookupError,json.JSONDecodeError):continue
     except Exception as exc:errors.append(str(exc));return
   watcher=threading.Thread(target=observe,daemon=True);watcher.start()
   cmd=['python3','tools/run_bounded.py','--run-id',rid,'--model-id','gpt-oss-120b-mxfp4-gguf','--backend','streaming','--backend-root',str(BACKEND),'--output-root',str(root/'raw'),'--variant','P12-slots40-ub32-passive-wait-'+rid,'--workload',str(IDS),'--cache-condition','fresh-pools-host-page-cache-uncontrolled','--timeout-s',str(p.get('capture_timeout_s',70)),'--resource-protocol',str(root/'protocol.json'),'--require-telemetry','--collect-start-inventory']
   for k,v in env.items():cmd+=['--env',k+'='+v]
   cmd+=['--',p['binary'],str(MODEL),str(IDS),str(capture),'--ngl','12']
   s=now()
   try:cp=subprocess.run(cmd,capture_output=True,text=True,timeout=min(p.get("capture_timeout_s",70)+70,end-time.monotonic()))
   finally:done.set();watcher.join(timeout=1)
   row={'run_id':rid,'start':s,'end':now(),'rc':cp.returncode,'stderr':cp.stderr[-2000:],'parallel_runtime':runtime,'runtime_errors':errors};rows.append(row);save(root/(rid+'-receipt.json'),row)
   if cp.returncode or errors or not runtime:raise ValueError('monitor/runtime failure '+str(row))
   manifest=read(str(stem)+'.json')
   if manifest['binary_sha256']!=p['binary_sha256'] or manifest['mapped_backend_libraries_sha256']!=p['libraries'] or manifest['explicit_env']!=env or manifest['resource_authority']!=p['resources'] or manifest['returncode'] or manifest['stop_reason'] or manifest['artifact_identity']['stat_at_launch']!=p['model_stat'] or manifest['artifact_identity']['stat_at_end']!=p['model_stat']:raise ValueError('bridge provenance/resources differ')
   for suffix,h in manifest['output_sha256'].items():
    if sha256(str(stem)+suffix)!=h:raise ValueError('bridge raw hash mismatch')
   if p.get('direct_witness_contract'):
    from c210_witness_gate import qualified
    if 'CANONICAL_DIRECT ' not in Path(str(stem)+'.stdout').read_text():raise ValueError('direct reader receipt absent')
    observed=qualified(capture)
    if i==0:
     original=qualified(Path(p['canonical_C127_ON']))
     if any(observed[k]!=original[k] for k in ('core','masks','logits')):raise ValueError('OBSERVER_NEUTRALITY_BLOCKED')
     save(root/'observer-neutrality.json',{'status':'PASS_BITWISE_SELECTED_SCOPE','states':250,'core_payloads':len(observed['core']),'full_logits':len(observed['logits']),'witness':observed['prospective_witness'],'canonical_C127_ON':p['canonical_C127_ON']})
    save(root/(rid+'-capture-manifest.json'),{'sha256':{str(f.relative_to(capture)):sha256(f) for f in capture.rglob('*') if f.is_file()},'bytes':sum(f.stat().st_size for f in capture.rglob('*') if f.is_file())})
    caps.append(observed)
   else:caps.append(inspect(capture,skip_on=True))
  a,b=caps
  equal=a['core']==b['core'] and a['masks']==b['masks'] and a['logits']==b['logits']
  save(root/'boundary-summary.json',{'status':'PASS_SAME_PROFILE_BITWISE' if equal else 'FAIL_SAME_PROFILE','states':250,'core_comparisons':len(a['core']),'full_logits':len(a['logits']),'controls':{'coverage_A':a['coverage'],'coverage_B':b['coverage'],'sentinels_A':a['sentinels'],'sentinels_B':b['sentinels']}})
  if not equal:raise ValueError('FAIL_SAME_PROFILE')
  status='PASS_H2_NUMERIC_BRIDGE'
 except Exception as exc:reason=type(exc).__name__+': '+str(exc)
 finally:
  finish=now();ep.record(root.name.split('-')[0]+'-passive-wait-numeric',start,finish,live=True,status=status,paths=[root/'decision.json'],worst_case_s=p.get("deadline_s",300))
  save(root/'decision.json',{'status':status,'reason':reason,'records':rows,'measurement_head':measurement,'start':start,'end':finish,'canonical_reference':'C127 unchanged shapes/device/libraries reused; no36-reference repeat','claim':'Selected189+32 same-profile bitwise, not production timing','publication':'LOCAL_ONLY'});save(root/'budget-checkpoint.json',ep.budget())
 print(status,reason,flush=True);return 0 if status=='PASS_H2_NUMERIC_BRIDGE' else 1

if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('mode',choices=('freeze','run'));q.add_argument('root',type=Path);q.add_argument('--epoch',type=Path);a=q.parse_args()
 if a.mode=='freeze':freeze(a.root,a.epoch)
 else:raise SystemExit(run(a.root))
