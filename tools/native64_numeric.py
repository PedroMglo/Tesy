"""C127 native64 qualification orchestration; original C75 and monitor reused."""
import argparse,json,os,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
from c2_gate import GateError
from c143_slots40_optin import identity,MODEL,BACKEND
from run_bounded import sha256,backend_library_hashes,file_identity,relevant_environment
from host_resource_policy import derive_policy,freeze_protocol_resource_limits,validate_resource_protocol
from c70_full_boundary_gate import inspect,compare
from c7_boundary_gate import phase_contract
from epoch_accounting import Epoch,now

IDS=Path('results/c2-target-numeric-v1.ids').resolve();CAP=18*2**30

def read(p):return json.loads(Path(p).read_text())
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
def frozen_identity(root):
    original,_,stat=identity();generation=read(root/'build/generation.json')
    binaries={k:str((root/'build'/k).resolve()) for k in ('capture','reference')}
    libs={k:backend_library_hashes(v,BACKEND) for k,v in binaries.items()}
    expected=read(Path('results/c127-slots40-numeric-20260929T1654Z/protocol.json'))['backend_libraries_sha256']
    if libs['capture']!=libs['reference'] or libs['capture']!=expected or any(original['identity']['library_sha256'].get(k)!=v for k,v in libs['capture'].items()):raise GateError('canonical/C75 core libraries differ')
    return {'model_stat':stat,'model_sha256_previously_verified':original['identity']['model_sha256'],'backend_sha':git('-C',str(BACKEND),'rev-parse','HEAD'),'binaries':binaries,'binary_sha256':{k:sha256(v) for k,v in binaries.items()},'library_sha256':libs['capture'],'numeric_ids_sha256':sha256(IDS),'generation':generation}
def freeze(root,epoch):
    p=read(root/'resource-policy.json');s=read(root/'snapshot.json')
    if derive_policy(snapshot=s)!=p or p['memory']['cap_max_bytes']<CAP:raise GateError('E18 not admitted')
    phases,masks=phase_contract(64)
    contract={'schema':'native64-numeric-v1','profile_id':'C75-P12-slots40-nativeub64-ctx8192-medium','identity':frozen_identity(root),'resources':freeze_protocol_resource_limits(p,cgroup_memory_max_bytes=CAP),'start_inventory':{'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(root/'resource-policy.json')},'limits':{},'call_plan':{'external_prefill':189,'internal_prefill':[64,64,61],'phases':phases,'masked':masks,'decode_teacher_forced':32,'decode_selected':[0,1,7,31],'full_logits':5},'gates':'Same-profile OFF/ON bitwise selected core routers/weights/FFN and five full logits; all36 native canonical resident FFN bitwise; no cross-profile equality claim','captures_model_timeout_s':90,'reference_model_timeout_s':30,'reference_group_timeout_s':180,'unit_live_timeout_s':int(600-Epoch(epoch).budget()['physical_used_s']-2),'raw_projection_bytes':512*2**20,'epoch':str(epoch),'publication':'LOCAL_ONLY','default_changed':False}
    validate_resource_protocol(contract);save(root/'protocol.json',contract)
def verify_run(stem,p,binary,env):
    m=read(str(stem)+'.json')
    for suffix,h in m['output_sha256'].items():
        if sha256(str(stem)+suffix)!=h:raise GateError('raw SHA differs')
    if m['returncode']!=0 or m['stop_reason'] is not None:raise GateError('monitor/process failure '+str(m['stop_reason']))
    i=p['identity']
    if m['binary_sha256']!=i['binary_sha256'][binary] or m['mapped_backend_libraries_sha256']!=i['library_sha256'] or m['backend_sha']!=i['backend_sha'] or m['artifact_identity']['stat_at_launch']!=i['model_stat'] or m['artifact_identity']['stat_at_end']!=i['model_stat'] or m['explicit_env']!=env or m['resource_authority']!=p['resources']:raise GateError('numeric provenance differs')
    return m

def run(root):
    p=read(root/'protocol.json');epoch=Epoch(p['epoch']);start=now();records=[];status='FAIL_EVIDENCE_OR_RESOURCES';reason=None
    if git('status','--porcelain') or relevant_environment(os.environ):raise GateError('measurement worktree/environment not clean')
    if p['identity']!=frozen_identity(root):raise GateError('frozen identity changed')
    measurement=git('rev-parse','HEAD');deadline=time.monotonic()+p['unit_live_timeout_s']
    if not epoch.budget(p['unit_live_timeout_s'],p['raw_projection_bytes'])['admitted']:raise GateError('unit budget not admitted')
    def execute(rid,binary,args,timeout,env,inventory=False,group_deadline=None):
        remain=min(deadline,group_deadline or deadline)-time.monotonic()
        allowance=timeout+(65 if inventory else 0)+5
        if remain<allowance:raise GateError('frozen full subprocess worst-case does not fit remaining unit')
        stem=root/'raw'/rid
        cmd=['python3','tools/run_bounded.py','--run-id',rid,'--model-id','gpt-oss-120b-mxfp4-gguf','--backend','streaming','--backend-root',str(BACKEND),'--output-root',str((root/'raw').resolve()),'--variant','P12-slots40-native64-'+rid,'--workload',str(IDS if binary=='capture' else args[1]+'/index.tsv'),'--cache-condition','fresh-pools-page-cache-uncontrolled' if binary=='capture' else 'resident-one-layer','--timeout-s',str(timeout),'--resource-protocol',str((root/'protocol.json').resolve()),'--require-telemetry']
        if inventory:cmd+=['--collect-start-inventory']
        for k,v in env.items():cmd+=['--env',k+'='+v]
        cmd+=['--',p['identity']['binaries'][binary],*args]
        child_start=now();proc=subprocess.run(cmd,timeout=min(remain,allowance+1),capture_output=True,text=True)
        row={'run_id':rid,'start':child_start,'end':now(),'measurement_head':measurement,'monitor_rc':proc.returncode,'monitor_stderr_tail':proc.stderr[-1500:]};records.append(row)
        save(root/(rid+'-launch.json'),row)
        if proc.returncode:raise GateError('monitor failed: '+row['monitor_stderr_tail'])
        m=verify_run(stem,p,binary,env);row.update(elapsed_model_s=m['elapsed_s'],maxima=m['maxima'],manifest_sha256=sha256(str(stem)+'.json'));return stem,m
    try:
        caps={}
        for arm in ('off','on'):
            rid='c191-native64-'+arm;caps[arm]=root/'raw'/(rid+'.capture')
            stem,m=execute(rid,'capture',[str(MODEL),str(IDS),str(caps[arm].resolve()),'--ngl','12'],p['captures_model_timeout_s'],{'TESY_CPU_WAVE_SKIP_PARKED':'1'} if arm=='on' else {},True)
            receipt=inspect(caps[arm],skip_on=arm=='on',ubatch=64)
            save(root/(rid+'-receipt.json'),{'status':'PASS_CAPTURE_ARM','coverage':receipt['coverage'],'sentinels':receipt['sentinels'],'manifest_sha256':sha256(str(stem)+'.json')})
            print(rid+' PASS_CAPTURE_ARM',flush=True)
        boundary=compare(caps['off'],caps['on'],ubatch=64);save(root/'boundary-summary.json',boundary)
        if boundary['status']!='SAME_PROFILE_BITWISE_PASS':raise GateError('same-profile OFF/ON mismatch')
        group_end=time.monotonic()+180
        refs=[]
        phases,_=phase_contract(64)
        for layer in range(36):
            rid=f'c191-native64-ref-l{layer:02}'
            stem,m=execute(rid,'reference',[str(MODEL),str(caps['on'].resolve()),str(layer),'--ngl','12'],30,{},False,group_end)
            result=read(str(stem)+'.stdout');expected='cpu' if layer<25 else 'gpu'
            if result['layer']!=layer or result['device']!=expected or [r['phase'] for r in result['rows']]!=list(phases) or result['numeric_rows']!=(5 if layer==35 else 7) or result['masked_rows']!=(2 if layer==35 else 0) or result['canonical_layer_bytes']!=1697956352:raise GateError('reference64 identity/coverage invalid')
            for r in result['rows']:
                if r['state']=='N/A_MASKED':
                    if layer!=35 or r['phase'] not in phases[:2]:raise GateError('wrong masked reference')
                elif not all((r['state']=='NUMERIC',r['routing_ids_equal'],r['routing_weights_bitwise'],r['ffn_bitwise'],r['routing_weights_nonfinite']==0,r['ffn_nonfinite']==0)):raise GateError('canonical same-profile mismatch layer '+str(layer))
            if not result['all_bitwise']:raise GateError('canonical reference aggregate mismatch')
            refs.append({'layer':layer,'status':'PASS','manifest_sha256':sha256(str(stem)+'.json'),'result_sha256':sha256(str(stem)+'.stdout')});save(root/(rid+'-receipt.json'),refs[-1]);print(rid+' PASS',flush=True)
        save(root/'reference-summary.json',{'status':'PASS_FULL_REFERENCE','layers':refs});status='PASS_NATIVE64_NUMERIC_SELECTED_SCOPE'
    except Exception as exc:reason=type(exc).__name__+': '+str(exc)
    finally:
        end=now();epoch.record('c191-N-numeric',start,end,live=True,status=status,paths=[root/'decision.json'],worst_case_s=p['unit_live_timeout_s'])
        save(root/'decision.json',{'status':status,'reason':reason,'measurement_head':measurement,'records':records,'start':start,'end':end,'claim':'189+32 native64 same-profile selected FFN/full logits, not full8K KV/attention or speed','W':'NOT_RUN_PENDING_N' if status.startswith('PASS') else 'NOT_RUN_NUMERIC_GATE','publication':'LOCAL_ONLY'})
        save(root/'budget-checkpoint.json',epoch.budget())
    print(json.dumps({'status':status,'reason':reason}),flush=True);return 0 if status.startswith('PASS') else 1
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=('freeze','run'));a.add_argument('root',type=Path);a.add_argument('--epoch',type=Path);v=a.parse_args()
    if v.mode=='freeze':freeze(v.root,v.epoch)
    else:raise SystemExit(run(v.root))
