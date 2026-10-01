"""Native32/64 natural utility family through the existing guarded C2 server."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

import c2_server_run as server
import c112_nominal_session_base as base
from c17_thermal_recovery import no_other_model
from c118_start_inventory import collect, require_inventory
from c9_server_admission import MODEL, validate_receipt
from c85_request_markers import validate as validate_markers
from epoch_accounting import Epoch, now
from host_resource_policy import validate_resource_protocol
from native64_numeric import read, save, git, CAP, BACKEND
from native64_evaluate import evaluate
from native64_sql import PROMPT, FIXTURES, expected, grade
from run_bounded import sha256, relevant_environment

IDS = ('c112-code','c112-repeat','native64-sql')
S_ORDER = ('A32','B64','B64','A32')
C_ORDER = ('A32','B64','B64','A32','A32','B64')
SOURCES = ('tools/native64_natural.py','tools/native64_sql.py','tools/native64_evaluate.py',
           'tools/c2_server_run.py','tools/request_evidence.py','tools/c118_start_inventory.py',
           'tools/host_resource_policy.py','tools/c112_nominal_session_base.py',
           'tools/epoch_accounting.py','tools/c9_server_admission.py','tools/c85_request_markers.py')

def unit(run_id):
    return 'tesy-'+run_id

def tasks(root):
    data=read(root/'session-input.json')
    first='Context: '+'alpha '*data['base_prefix_words']+data['first_question']
    second=' beta'*data['increment_beta_words']+data['second_question']
    return [(rid,{'id':rid,'category':'native64-useful-natural',
        'messages':[{'role':'user','content':text}],'cache_prompt':True,
        'chat_template_kwargs':{'tesy_template_date':data['template_date']}})
        for rid,text in zip(IDS,(first,second,PROMPT))]

def make(root,run_id,profile):
    base.BACKENDS={k:(BACKEND,'build-c75-cuda','27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5',
                          {'TESY_CPU_WAVE_SKIP_PARKED':'1'}) for k in ('control','candidate')}
    base.input_row=lambda unused:read(root/'session-input.json')
    protocol,config=base.make(root,'control' if profile=='A32' else 'candidate')
    cmd=config['server_command'];cmd[cmd.index('--moe-stream-cache')+1]='40s'
    cmd[cmd.index('-ub')+1]='32' if profile=='A32' else '64'
    config.update(suite='native64natural',task_ids=list(IDS),total_timeout_s=230,
        readiness_timeout_s=30,require_natural_stop=True,
        per_task_request_policy={IDS[0]:{'max_tokens':256,'per_request_timeout_s':180},
                                 IDS[1]:{'max_tokens':256,'per_request_timeout_s':90},
                                 IDS[2]:{'max_tokens':384,'per_request_timeout_s':120}},
        prompt_token_ranges={IDS[0]:[1980,2150],IDS[1]:[2100,2500],IDS[2]:[2100,3500]})
    config['request_policy']['per_request_timeout_s']=180
    protocol['schema_version']='native64-natural-v1';protocol['protocol_id']=run_id+'-v1'
    protocol['expected_request_ids']=list(IDS)
    prior=protocol.pop('c97')
    protocol['native64']={'profile':profile,'run_id':run_id,'model_stat':prior['model_stat'],
         'backend_tree':prior['backend_tree'],'numeric_decision_sha256':sha256(
             base.REPO/'results/c191-native64-numeric-20260930T2055Z/decision.json'),
         'source_sha256':{p:sha256(base.REPO/p) for p in SOURCES},
         'workload_sha256':sha256(root/'workload.json')}
    protocol['execution_scope_unit']=unit(run_id)
    protocol['identity']['config_sha256']=server.digest(config)
    protocol['start_inventory']={'schema':'c120-start-inventory-v1','duration_s':60,
        'max_age_s':3,'policy_sha256':sha256(root/'resource-policy.json')}
    validate_resource_protocol(protocol)
    return protocol,config

def freeze(root,epoch_path,confirmation=False):
    count=6 if confirmation else 4;maximum=1800 if confirmation else 1200
    epoch=Epoch(epoch_path)
    admission=epoch.budget(maximum,32*2**20)
    if not admission['admitted']:raise ValueError('whole natural family plus closure not admitted')
    for name in ('snapshot.json','resource-policy.json'):
        save(root/name,read(epoch_path/name))
    data=read(base.REPO/'results/c129-slots40-confirm-20260929T1735Z/session-input.json')
    # The prompts remain original; one date is frozen for all natural requests/arms.
    data['template_date']='2026-09-30';data['requests']=3
    save(root/'session-input.json',data)
    save(root/'workload.json',{'schema':'native64-natural-workload-v1','tasks':tasks(root),
        'sql_fixtures':FIXTURES,'sql_expected':[expected(r) for r in FIXTURES],
        'sql_envelope':'pure SELECT/WITH or exactly one sql/sqlite code block; no prose',
        'sql_execution':'SQLite in-memory isolated, query_only + restrictive authorizer, no extensions, 100000 instructions/2s',
        'nominal153_anchor':{'official_T1':2043,'official_T2':2197,'cache_n':2044,'prompt_n':153},
        'history':'actual final assistant content from each arm; differing reasoning/outputs retained',
        'output_ids':'NOT_EXPOSED unless native response actually exposes nonempty IDs; no retokenization'})
    order=C_ORDER if confirmation else S_ORDER
    run_ids=[f'{root.name.split("-")[0]}-{i+1}-{p}' for i,p in enumerate(order)]
    save(root/'protocol.json',{'schema':'native64-natural-family-v1','epoch':str(epoch_path),
        'confirmation':confirmation,'order':list(zip(run_ids,order)),'maximum_live_s':maximum,
        'arm_maximum_s':300,'unit_runtime_max_s':295,'unit_stop_grace_s':3,
        'server_timeout_s':230,'readiness_s':30,'request_deadlines_s':[180,90,120],
        'claim':'natural utility; histories and output work may differ; W is fixed-input protection',
        'primary':'T2 first final >=15% median and all gains positive',
        'sql_primary':'>=8% median/all positive' if confirmation else '>=0% median',
        'protections':'all frozen natural metrics median >=-5%; correctness/resources/prefix/nominal153 PASS',
        'no_retry':True,'publication':'LOCAL_ONLY','source_sha256':{p:sha256(base.REPO/p) for p in SOURCES},
        'workload_sha256':sha256(root/'workload.json'),'budget_admission':admission})
    for rid,profile in zip(run_ids,order):
        p,c=make(root,rid,profile);save(root/'protocols'/(rid+'.json'),p);save(root/(rid+'-config.json'),c)
    save(root/'freeze-manifest.json',{'sha256':{str(p.relative_to(root)):sha256(p) for p in root.rglob('*.json')},'created_at':now(),'no_hash_of_own_commit':True})

def require_freeze(root):
    manifest=read(root/'freeze-manifest.json')
    for name,digest in manifest['sha256'].items():
        if sha256(root/name)!=digest:raise ValueError('frozen artifact changed: '+name)


def checker():
    previous=[None]
    def validate(rid,item):
        text=item['message']['content'].strip()
        if rid==IDS[0]:
            if not re.fullmatch(r'[0-9]{5}',text):raise ValueError('CONTENT_T1_INVALID')
            previous[0]=text;return {'PASS':True,'scope':'five-digit code'}
        if rid==IDS[1]:
            if text!=previous[0]:raise ValueError('CONTENT_T2_HISTORY_INVALID')
            return {'PASS':True,'scope':'exact actual prior final answer'}
        result=grade(text)
        # Validation completes before server cleanup, directly after the HTTP completion.
        result['validated_monotonic_s']=time.monotonic()
        return result
    return validate

def analyze_arm(root,rid,profile,p,c):
    raw=read(root/'raw'/(rid+'.json'))
    samples=[json.loads(x) for x in (root/'raw'/(rid+'.samples.jsonl')).read_text().splitlines()]
    maxima=validate_receipt(p,c,raw,samples,root,run_id=rid,
        protocol_filename='protocols/'+rid+'.json',expected_results=3)
    if raw['preflight']['ready_elapsed_s']>30:raise ValueError('readiness30 exceeded')
    ids=read(root/'raw'/(rid+'.tokenization.json'))
    if list(ids)!=list(IDS):raise ValueError('official IDs incomplete')
    validate_markers(root/'raw'/(rid+'.request-markers.jsonl'),rid,IDS,raw['results'])
    reports=[]
    for i,item in enumerate(raw['results']):
        timings=item['timings'];stream=item['stream_metrics'];cap=256 if i<2 else 384
        if not item['accepted'] or item['finish_reason']!='stop' or not stream['done_observed'] or not 0<item['usage']['completion_tokens']<cap or item['usage']['prompt_tokens']!=len(ids[item['id']]):raise ValueError('natural/accounting incomplete')
        if timings['cache_n']+timings['prompt_n']!=len(ids[item['id']]):raise ValueError('native prefix accounting incoherent')
        validation=item.get('functional_validation')
        if not validation or not validation['PASS']:raise ValueError('functional validation absent')
        reports.append({'request_id':item['id'],'official_ids':len(ids[item['id']]),
            'input_ids_sha256':server.digest(ids[item['id']]),'output_ids':'NOT_EXPOSED',
            'output_tokens':item['usage']['completion_tokens'],'finish_reason':item['finish_reason'],
            'native_timings':timings,'stream_metrics':stream,
            'request_wall_s':item['ended_s']-item['started_s'],
            'final_content_sha256':server.digest(item['message']['content']),
            'functional_validation':validation})
    t1,t2,t3=raw['results'];a,b=ids[IDS[0]],ids[IDS[1]]
    common=next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))
    server.validate_generated_prefix_cache(a,b,t2['timings']['cache_n'],t2['timings']['prompt_n'],t1['usage']['completion_tokens'],1900,32)
    nominal=(len(a),len(b),t2['timings']['cache_n'],t2['timings']['prompt_n'])==(2043,2197,2044,153)
    ff=lambda r:r['stream_metrics']['first_final_content_chunk_s']
    sql_started=t3['deadline_monotonic']-120
    return {'run_id':rid,'profile':profile,'complete':True,'natural':True,'identity':True,
        'resources':True,'deadline':True,'samples':True,'functional':True,'prefix':True,
        'nominal153':nominal,'common_prefix_T2':common,'requests':reports,'maxima':maxima,
        'T2_first_final_s':ff(t2),'SQL_validated_s':t3['functional_validation']['validated_monotonic_s']-sql_started,
        'cold_prefill_s':t1['timings']['prompt_ms']/1000,'cold_first_final_s':ff(t1),
        'T2_completion_s':t2['ended_s']-t2['started_s'],'T3_first_final_s':ff(t3),
        'incremental_prefill_s':t2['timings']['prompt_ms']/1000,
        'decode_seconds_per_reported_output':t2['timings']['predicted_ms']/1000/t2['timings']['predicted_n'],
        'decode_convention':'C75 n_decoded/t_token_generation as predicted_n/predicted_ms; natural descriptive, not equal compute',
        'raw_sha256':sha256(root/'raw'/(rid+'.json'))}

def arm(root,rid,measurement,*,hooks=None):
    root=root.resolve()
    hooks=hooks or {};cap=hooks.get('cap',CAP)
    start=now();failure=None;row=None
    try:
        require_freeze(root)
        family=read(root/'protocol.json');profile=dict(family['order'])[rid]
        p=read(root/'protocols'/(rid+'.json'));c=read(root/(rid+'-config.json'))
        if git('rev-parse','HEAD')!=measurement or relevant_environment(os.environ):raise ValueError('measurement/environment changed')
        if any(sha256(base.REPO/k)!=v for k,v in family['source_sha256'].items()) or sha256(root/'workload.json')!=family['workload_sha256']:raise ValueError('frozen source/workload changed')
        if server.digest(c)!=p['identity']['config_sha256'] or p.get('portfolio',p.get('native64'))['profile']!=profile:raise ValueError('frozen profile/config changed')
        no_other_model()
        policy=read(root/'resource-policy.json');power={k:policy['power'][k] for k in ('source','profile')}
        inv=collect(root,rid,policy=policy,cap_bytes=cap,expected_power=power,duration_s=60)
        save(root/'raw'/(rid+'.start-inventory.receipt.json'),inv)
        require_inventory(root,rid,inv,policy=policy,cap_bytes=cap,expected_power=power,duration_s=60)
        args=SimpleNamespace(run_id=rid,protocol=root/'protocols'/(rid+'.json'),suite=hooks.get('suite','native64natural'),model='target120b')
        code=server.run(args,p,c,hooks.get('tasks',tasks)(root),MODEL,result_validator=hooks.get('checker',checker)())
        if code and not hooks.get('accept_terminal_censor',lambda *_:False)(root,rid):raise ValueError('server response/resource/identity gate failed; raw preserved')
        row=hooks.get('analyze',analyze_arm)(root,rid,profile,p,c)
        if now()['monotonic_s']-start['monotonic_s']>family.get('arm_maximum_s',300):raise ValueError('arm envelope exceeded')
    except Exception as exc:failure=type(exc).__name__+': '+str(exc)
    receipt={'status':'PASS_NATURAL_ARM' if failure is None else 'FAIL_OR_INCOMPLETE_NATURAL_ARM',
        'reason':failure,'run_id':rid,'start':start,'end':now(),'measurement_head':measurement,
        'row':row,'no_retry':True}
    save(root/(rid+'-receipt.json'),receipt);print(json.dumps(receipt),flush=True)
    return 0 if failure is None else 1

def family(root,*,hooks=None):
    root=root.resolve()
    hooks=hooks or {};cap=hooks.get('cap',CAP)
    require_freeze(root)
    p=read(root/'protocol.json');ep=Epoch(p['epoch']);start=now();rows=[];failure=None;status='FAIL_OR_INCOMPLETE_EVIDENCE'
    measurement=git('rev-parse','HEAD')
    if git('status','--porcelain') or not ep.budget(p['maximum_live_s']+p.get('remaining_reserved_live_s',0),32*2**20+p.get('remaining_reserved_raw_bytes',0))['admitted']:raise ValueError('natural freeze not clean/admitted')
    try:
        for rid,profile in p['order']:
            command=['systemd-run','--user','--unit='+unit(rid),'--wait','--collect',
                '--property=MemoryMax='+str(cap),'--property=MemoryHigh='+str(cap),
                '--property=MemorySwapMax=0','--property=RuntimeMaxSec='+str(p.get('unit_runtime_max_s',295)),'--property=TimeoutStopSec=3',
                '--working-directory='+str(base.REPO),'--setenv=PYTHONPATH=tools','--setenv=PYTHONDONTWRITEBYTECODE=1',
                '/usr/bin/python3',hooks.get('arm_script','tools/native64_natural.py'),'arm',str(root),'--run-id',rid,'--measurement-head',measurement]
            arm_started=now()
            completed=subprocess.run(command,capture_output=True,text=True,timeout=p.get('arm_maximum_s',300))
            if completed.returncode:raise ValueError('natural arm failed '+rid+': '+completed.stderr[-600:])
            receipt=read(root/(rid+'-receipt.json'))
            if receipt['status']!='PASS_NATURAL_ARM' or now()['monotonic_s']-arm_started['monotonic_s']>p.get('arm_maximum_s',300):raise ValueError('natural arm invalid/envelope exceeded')
            rows.append(receipt['row']);print(json.dumps({'arm':rid,'first_final_T2_s':rows[-1]['T2_first_final_s'],'SQL_validated_s':rows[-1]['SQL_validated_s'],'nominal153':rows[-1].get('nominal153')}),flush=True)
        pairs=[(rows[0],rows[1]),(rows[3],rows[2])]
        if p['confirmation']:pairs.append((rows[4],rows[5]))
        result=hooks.get('evaluate',lambda v:evaluate(v,'S',confirmation=p['confirmation']))(pairs);status=result['status'];save(root/'paired-metrics.json',result)
    except Exception as exc:
        failure=type(exc).__name__+': '+str(exc)
        # These are our own uniquely frozen scopes; never touch the usual service.
        for rid,_ in p['order']:
            subprocess.run(['systemctl','--user','stop',unit(rid)+'.service'],capture_output=True,timeout=8)
    finally:
        end=now();ep.record(root.name.split('-')[0]+'-natural-family',start,end,live=True,status=status,paths=[root/'decision.json'])
        save(root/'decision.json',{'status':status,'reason':failure,'measurement_head':measurement,
            'arms':rows,'start':start,'end':end,'confirmation':p['confirmation'],'publication':'LOCAL_ONLY',
            'claim':p.get('claim','Natural utility with own real history; different output work retained, not same-compute speedup')})
        save(root/'budget-checkpoint.json',ep.budget())
    print(status,failure,flush=True);return 0 if status in ('GO_S_SCREEN','GO_S_CONFIRMATION','GO_SCREEN','GO_CONFIRMATION') else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('freeze','arm','family'))
    parser.add_argument('root',type=Path);parser.add_argument('--epoch',type=Path)
    parser.add_argument('--confirmation',action='store_true');parser.add_argument('--run-id');parser.add_argument('--measurement-head')
    args=parser.parse_args()
    if args.mode=='freeze':freeze(args.root,args.epoch,args.confirmation)
    elif args.mode=='arm':raise SystemExit(arm(args.root,args.run_id,args.measurement_head))
    else:raise SystemExit(family(args.root))
