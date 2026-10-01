import json,pathlib,hashlib,sys,time
sys.path.insert(0,'tools')
from run_bounded import sha256,backend_library_hashes,file_identity
from c143_slots40_optin import identity,BACKEND,MODEL
from epoch_accounting import now,Epoch
from parallel_runtime import parallel_environment
from native64_numeric import read,save
r=pathlib.Path('results');
import argparse
p=argparse.ArgumentParser();p.add_argument('epoch',type=pathlib.Path);ep=p.parse_args().epoch;start=now();checks=[]
def manifest(p,select=None):
 d=read(p);rows=d.get('raw',d.get('files'));base=p.parent/'raw';count=0;total=0
 for k,v in rows.items():
  if select and not select(k):continue
  f=pathlib.Path(k) if k.startswith('results/') else base/k
  if f.stat().st_size!=v['bytes'] or sha256(f)!=v['sha256']:raise ValueError('raw corrupt '+str(f))
  count+=1;total+=v['bytes']
 checks.append({'manifest':str(p),'sha256':sha256(p),'verified_files':count,'verified_bytes':total})
manifest(r/'c140-slots44-numeric-20260929T2324Z/manifest.json')
manifest(r/'c142-uniform44-confirm-20260929T2353Z/manifest.json')
manifest(r/'c225-post-c209-passive-wait-closure-20261001/raw-manifest.json',lambda k:'/c211-' in k or '/c210-' in k)
# Validate C203 frozen inputs and native raw output-source manifests.
p=r/'c203-slots44-useful-screen-20261001';fr=read(p/'freeze-manifest.json')
for k,h in fr['sha256'].items():
 if sha256(p/k)!=h:raise ValueError('C203 freeze '+k)
for f in p.glob('raw/c203-*.json'):
 d=read(f)
 for suffix,h in d.get('source_sha256',{}).items():
  if sha256(p/'raw'/(f.stem+suffix))!=h:raise ValueError('C203 raw '+suffix)
checks.append({'C203':'freeze and all native raw source hashes verified','freeze_sha256':sha256(p/'freeze-manifest.json')})
old,c,stat=identity();current=read(r/'c210-post-c209-passive-wait-20261001T102645Z/runtime-reuse.json')
assert stat==current['model_stat'];assert sha256(c['server_command'][0])==current['server_sha256'];assert all(backend_library_hashes(c['server_command'][0],BACKEND).get(k)==h for k,h in current['backend_libraries_sha256'].items())
for n in ('c127-slots40-numeric-20260929T1654Z','c140-slots44-numeric-20260929T2324Z'):
 p=read(r/n/'protocol.json')
 for field in ('binary','reference_binary'):
  assert sha256(p[field+'_path'])==p[field+'_sha256']
 assert p['backend_libraries_sha256']==current['backend_libraries_sha256'];assert p['model_stat']==stat
for layer in range(36):
 f=r/'c140-slots44-numeric-20260929T2324Z'/f'c140-ref-l{layer:02}-01-receipt.json';assert sha256(f)==read(r/'c140-slots44-numeric-20260929T2324Z/manifest.json')['references'][layer]['receipt_sha256']
assert read(r/'c223-passive-wait-confirmation-20261001/decision.json')['status']=='NOT_RUN_S_GATE'
assert read(r/'c224-passive-wait-qualification-20261001/decision.json')['status']=='NOT_RUN_NO_CONFIRMED_WINNER'
assert not list((r/'c223-passive-wait-confirmation-20261001/raw').glob('*'))
# Original build recipe flags remain byte-identical.
m=read(r/'c208-post-c198-portfolio-closure-20261001/profile-identity-manifest.json')['manifest']
for key,file in [('CMake_cache_sha256','CMakeCache.txt'),('compile_commands_sha256','compile_commands.json')]:assert sha256(BACKEND/'build-c75-cuda'/file)==m[key]
policy=read(ep/'resource-policy.json');cap=min(20*2**30,policy['memory']['cap_max_bytes'])//(256*2**20)*(256*2**20);assert cap>=18*2**30
# Each unmeasured scope44: corresponding original scope40 peak + real CPU copies +1GiB uncertainty.
basepeaks={'C':15893782528,'Qfunc':15750131712,'Qlaunch':15893782528,'Q8K':15722098688};inc=1321920000
projection={k:{'base40_peak_bytes':v,'CPU_additional_copies_bytes':inc,'host_uncertainty_bytes':2**30,'projected_host_peak_bytes':v+inc+2**30,'preventive_guard_bytes':cap-512*2**20,'admitted':v+inc+2**30<cap-512*2**20} for k,v in basepeaks.items()}
assert all(v['admitted'] for v in projection.values())
gpu=6900+581644800/2**20;assert gpu<policy['gpu']['memory_stop_total_mib']
save(ep/'reuse-and-capacity.json',{'status':'IDENTITY_AND_CAPACITY_ESTIMATE_PASS','C140_C142_C203_C211':checks,'runtime':current,'C188':'Original server/libs/model and invocation recipe intact; no new40inference','build_flags':'CMakeCache/compile_commands original bytes verified','source':'C75original clean; graphs/kernels/runtime not rebuilt','parallel_environment':parallel_environment(__import__('os').environ),'cap_bytes':cap,'cap_formula':'floor256MiB(min20GiB,cap_max_live)','projected_host_by_phase':projection,'GPU':{'base_observed_high_mib':6900,'additional_bytes':581644800,'projected_total_mib':gpu,'guard_total_mib':policy['gpu']['memory_stop_total_mib'],'remaining_to_guard_mib':policy['gpu']['memory_stop_total_mib']-gpu,'scope':'ESTIMADO, includes existing fullctx8192 KV; preventive512MiB GPU reserve remains, forward monitor authoritative'},'JSON_holdout':'C223 frozen NOT_RUN verified; no call so far','model':'Stat verified, original whole-file SHA reused; no weights rehash/page warmup'})
Epoch(ep).record('identity-raw-hash-revalidation',start,now(),live=False,status='HASHES_PASS',paths=[ep/'reuse-and-capacity.json'])
print('PASS cap',cap,'projections',projection)
