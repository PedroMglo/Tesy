#!/usr/bin/env python3
"""Explicit bounded opt-in C75 slots40 service; no default or permanent activation."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import c55_inventory
from c2_gate import GateError,strict_json
from c17_thermal_recovery import no_other_model
from host_resource_policy import derive_policy,freeze_protocol_resource_limits,validate_resource_protocol
from run_bounded import backend_library_hashes,file_identity,sha256,relevant_environment

REPO=Path(__file__).resolve().parents[1]
CAP=18*2**30
SOURCE=REPO/'results/c129-slots40-confirm-20260929T1735Z'
MODEL=Path('/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf')
BACKEND=Path('/tmp/tesy-c75-backend-20260928')
BACKEND_SHA='27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5'
PROFILE='slots40'
CONFIG_NAME='c129-p1-candidate'

def select_profile(profile,cap_bytes=None):
    global SOURCE,BACKEND,BACKEND_SHA,PROFILE,CONFIG_NAME,CAP
    PROFILE=profile
    CAP=18*2**30
    if profile=='slots40':
        SOURCE=REPO/'results/c129-slots40-confirm-20260929T1735Z';BACKEND=Path('/tmp/tesy-c75-backend-20260928')
        BACKEND_SHA='27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5';CONFIG_NAME='c129-p1-candidate'
    elif profile=='c35':
        SOURCE=REPO/'results/c121-nominal153-20260929T1350Z';BACKEND=Path('/tmp/tesy-c35-backend-20260928')
        BACKEND_SHA='c3759bad92c0e6f71bb936afea9b0a162fb83f76';CONFIG_NAME='c121-p1-control'
    elif profile=='slots40-persistent':
        if cap_bytes!=20*2**30:raise GateError('persistent R0 needs explicit frozen 20GiB cap')
        CAP=cap_bytes
        SOURCE=REPO/'results/c281-persistent-r0-runtime-20261005';BACKEND=REPO/'backends/c269-layer-last-use'
        BACKEND_SHA='d0ebfbcc6c8f456bc1083027c1b08075a32824d8';CONFIG_NAME='c281-r0-persistent'
    elif profile=='slots44':
        if type(cap_bytes) is not int or not 18*2**30<=cap_bytes<=20*2**30 or cap_bytes%(256*2**20):
            raise GateError('slots44 needs explicit admitted common cap, 18-20GiB/256MiB aligned')
        CAP=cap_bytes
        SOURCE=REPO/'results/c142-uniform44-confirm-20260929T2353Z';BACKEND=Path('/tmp/tesy-c75-backend-20260928')
        BACKEND_SHA='27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5';CONFIG_NAME='c142-p1-candidate'
    else:raise GateError('unknown explicit profile')


def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def identity():
    if PROFILE=='slots40-persistent' and not (SOURCE/'protocols'/f'{CONFIG_NAME}.json').is_file():raise GateError('persistent R0 manifest absent; manual reconstruction and requalification required')
    p=strict_json((SOURCE/'protocols'/f'{CONFIG_NAME}.json').read_text())
    c=strict_json((SOURCE/f'{CONFIG_NAME}-config.json').read_text());cmd=c['server_command']
    actual=subprocess.check_output(['git','-C',str(BACKEND),'rev-parse','HEAD'],text=True).strip()
    if actual!=BACKEND_SHA or subprocess.check_output(['git','-C',str(BACKEND),'status','--porcelain'],text=True):
        raise GateError('opt-in pinned backend source changed')
    if sha256(cmd[0])!=p['identity']['binary_sha256'] or backend_library_hashes(cmd[0],BACKEND)!=p['identity']['library_sha256']:
        raise GateError('opt-in pinned backend binary/library hash changed')
    if PROFILE=='slots40-persistent':
        from parallel_runtime import validate_launch_runtime
        validate_launch_runtime(p['parallel_runtime'],dict(os.environ,**c['explicit_env']))
        for name,expected in p['extra_library_sha256'].items():
            if not Path(name).is_file() or sha256(name)!=expected:raise GateError('persistent server dependency missing/changed: '+name)
    stat=file_identity(MODEL);old=p['c120']['model_stat']
    if (stat['dev'],stat['inode'],stat['size_bytes'],stat['mtime_ns'])!=(old['dev'],old['ino'],old['size'],old['mtime_ns']):
        raise GateError('opt-in model stat changed; content must be reverified before using')
    return p,c,stat


def configured_command(config,port,date):
    command=list(config['server_command']);command[command.index('--port')+1]=str(port)
    command[command.index('--chat-template-kwargs')+1]=json.dumps({'reasoning_effort':'medium','tesy_template_date':date},sort_keys=True)
    return command

def prepare(root,port,duration):
    if relevant_environment(os.environ):raise GateError('clear inherited LLAMA/TESY/GGML/CUDA/LD overrides before explicit opt-in')
    if root.exists():raise GateError('opt-in session root must be new')
    if not 1024<=port<=65535 or not 60<=duration<=7200:raise GateError('invalid explicit port/session duration')
    no_other_model()
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    p,c,stat=identity();root.mkdir(parents=True);(root/'raw').mkdir()
    c55_inventory.run(root);policy=strict_json((root/'resource-policy.json').read_text())
    if os.statvfs(root).f_bavail*os.statvfs(root).f_frsize<11*2**30:raise GateError('opt-in reserve1GiB raw plus10GiB free required')
    if derive_policy(snapshot=strict_json((root/'snapshot.json').read_text()))!=policy or policy['memory']['cap_max_bytes']<CAP:
        raise GateError('opt-in frozen cap/reserve not admitted')
    date=datetime.now(timezone.utc).date().isoformat();rid='tesy-optin-'+PROFILE+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    command=configured_command(c,port,date)
    preset={'schema':'tesy-slots40-optin-v1','status':'SESSION_PROFILE_IMPROVED_M4_NOT_MET' if PROFILE in ('slots40','slots40-persistent') else 'CONTROL_C35_TESTED_SCOPE','profile':PROFILE,'run_id':rid,
        'backend_sha':BACKEND_SHA,'binary_sha256':p['identity']['binary_sha256'],'library_sha256':p['identity']['library_sha256'],
        'model_sha256_previously_verified':p['identity']['model_sha256'],'model_stat':stat,
        'source_configuration_sha256':sha256(SOURCE/f'{CONFIG_NAME}-config.json'),
        'launcher_sha256':sha256(__file__),'monitor_sha256':sha256(REPO/'tools/run_bounded.py'),'prepare_source_commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),'server_command':command,'explicit_env':c['explicit_env'],
        'session_date':date,'duration_s':duration,'port':port,'cap_bytes':CAP,'swap_max_bytes':0,
        'default_changed':False,'publication':'LOCAL_ONLY_PRIVATE_SESSION_ROOT',
        'reuse':'same process/model/template/profile/date/KV only; restart persistence NOT_RUN'}
    if PROFILE=='slots40-persistent':
        preset['parallel_runtime']=p['parallel_runtime']
        preset['extra_library_sha256']=p['extra_library_sha256']
        preset['coverage']='R0 reconstructed selected bridge; two-request launcher restoration; M3 PARTIAL; M4 NOT_MET'
    if PROFILE=='slots44':
        from parallel_runtime import parallel_environment
        preset['status']='RESEARCH_QUALIFICATION_ONLY_NOT_DELIVERED'
        preset['parallel_environment']=parallel_environment(dict(os.environ,**c['explicit_env']))
    resource={'schema':'tesy-optin-start-v1','limits':{},'resources':freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP),
        'start_inventory':{'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(root/'resource-policy.json')},
        'preset_run_id':rid,'preset_sha256':__import__('host_resource_policy').digest(preset)}
    if PROFILE=='slots40-persistent':resource['parallel_runtime']=preset['parallel_runtime']
    validate_resource_protocol(resource);save(root/'preset.json',preset);save(root/'resource-protocol.json',resource)
    print(json.dumps({'status':'PREPARED_NOT_STARTED','root':str(root),'run_id':rid,'endpoint':f'http://127.0.0.1:{port}','session_date':date}))


def verified(root):
    if relevant_environment(os.environ):raise GateError('unexpected inherited backend environment')
    preset=strict_json((root/'preset.json').read_text());select_profile(preset['profile'],preset['cap_bytes'] if preset['profile'] in ('slots44','slots40-persistent') else None);protocol=strict_json((root/'resource-protocol.json').read_text())
    if PROFILE=='slots44':
        from parallel_runtime import parallel_environment
        if parallel_environment(dict(os.environ,**preset['explicit_env']))!=preset.get('parallel_environment') or 'GOMP_SPINCOUNT' in preset.get('parallel_environment',{}).get('values',{}):
            raise GateError('slots44 evaluated OpenMP environment changed')
    p,c,stat=identity()
    if preset['server_command']!=configured_command(c,preset['port'],preset['session_date']) or preset['explicit_env']!=c['explicit_env'] or preset['cap_bytes']!=CAP or preset['swap_max_bytes']!=0 or not 60<=preset['duration_s']<=7200 or preset['source_configuration_sha256']!=sha256(SOURCE/f'{CONFIG_NAME}-config.json'):
        raise GateError('opt-in frozen configuration/profile changed')
    if preset['model_stat']!=stat or preset['launcher_sha256']!=sha256(__file__) or preset['monitor_sha256']!=sha256(REPO/'tools/run_bounded.py') or \
       preset['binary_sha256']!=p['identity']['binary_sha256'] or preset['library_sha256']!=p['identity']['library_sha256'] or \
       __import__('host_resource_policy').digest(preset)!=protocol['preset_sha256'] or \
       preset['run_id']!=protocol['preset_run_id']:
        raise GateError('opt-in frozen preset identity changed')
    if PROFILE=='slots40-persistent' and (preset.get('parallel_runtime')!=p['parallel_runtime'] or protocol.get('parallel_runtime')!=p['parallel_runtime'] or preset.get('extra_library_sha256')!=p['extra_library_sha256']):raise GateError('persistent runtime contract changed')
    validate_resource_protocol(protocol)
    if protocol['resources']['cgroup']['memory_max_bytes']!=CAP:raise GateError('opt-in cap differs')
    return preset


def monitor_command(root,preset):
    return [sys.executable,str(REPO/'tools/run_bounded.py'),'--run-id',preset['run_id'],
        '--model-id','gpt-oss-120b-mxfp4-gguf','--backend','streaming','--backend-root',str(BACKEND),
        '--output-root',str(root/'raw'),'--variant',preset['profile']+'-P12-optin','--workload',str(root/'preset.json'),
        '--cache-condition','session-fresh-expert-pools-prefix-reuse-in-process','--timeout-s',str(preset['duration_s']),
        '--resource-protocol',str(root/'resource-protocol.json'),'--require-telemetry','--collect-start-inventory',
        *[arg for key,value in preset['explicit_env'].items() for arg in ('--env',key+'='+value)],'--',*preset['server_command']]


def start(root):
    p=verified(root);no_other_model()
    with socket.socket() as sock:sock.bind(('127.0.0.1',p['port']))
    if (root/'start-request.json').exists():raise GateError('session already attempted; create a new root')
    argv=['systemd-run','--user','--unit',p['run_id'],'--collect','--working-directory',str(REPO),
        '-p',f'MemoryMax={CAP}','-p',f'MemoryHigh={CAP}','-p','MemorySwapMax=0',
        '-p',f'RuntimeMaxSec={p["duration_s"]+90}','-p','TimeoutStopSec=15','-p','KillMode=control-group','--',
        sys.executable,str(Path(__file__).resolve()),'serve','--root',str(root)]
    result=subprocess.run(argv,capture_output=True,text=True)
    supervisor=None
    if result.returncode==0:
        from run_bounded import process_identity
        supervisor_pid=int(subprocess.check_output(['systemctl','--user','show',p['run_id']+'.service','-p','MainPID','--value'],text=True).strip())
        supervisor=process_identity(supervisor_pid)
        supervisor['executable']=os.path.realpath(f'/proc/{supervisor_pid}/exe')
    save(root/'start-request.json',{'supervisor_identity':supervisor,'status':'START_REQUESTED' if result.returncode==0 else 'FAIL_HARNESS_PREMODEL',
        'utc':datetime.now(timezone.utc).isoformat(),'argv':argv,'returncode':result.returncode,'stderr':result.stderr,
        'preset_sha256':sha256(root/'preset.json'),'requires':'model launch receipt in raw after fresh60s gate'})
    if result.returncode:raise GateError('own opt-in unit failed to start: '+result.stderr)
    print(json.dumps({'unit':p['run_id']+'.service','endpoint':f'http://127.0.0.1:{p["port"]}',
        'state':'WAITING_60S_INVENTORY; check /health before requests','root':str(root)}))


def stop(root):
    p=verified(root);launch=root/'raw'/f'{p["run_id"]}.launch.json'
    if not launch.is_file():
        request=strict_json((root/'start-request.json').read_text());expected=request.get('supervisor_identity')
        from run_bounded import process_identity
        if not expected:raise GateError('no own supervisor identity')
        pid=expected['pid'];actual=process_identity(pid)
        if actual!={k:v for k,v in expected.items() if k!='executable'} or os.path.realpath(f'/proc/{pid}/exe')!=expected['executable'] or not actual['cgroup_path'].endswith('/'+p['run_id']+'.service'):
            raise GateError('own premodel supervisor identity changed')
        save(root/'stop-request.json',{'status':'OWNER_CANCELLED_PREMODEL','supervisor_identity':expected,'utc':datetime.now(timezone.utc).isoformat()})
        subprocess.run(['systemctl','--user','stop',p['run_id']+'.service'],check=True)
        return
    row=strict_json(launch.read_text());expected=row['process_identity'];pid=expected['pid']
    from run_bounded import process_identity
    if process_identity(pid)!=expected or Path(os.path.realpath(f'/proc/{pid}/exe'))!=Path(p['server_command'][0]).resolve() or \
       not expected['cgroup_path'].endswith('/'+p['run_id']+'.service'):
        raise GateError('own model PID/start ticks/executable/scope identity changed')
    save(root/'raw'/f'{p["run_id"]}.owner-stop.json',{'status':'INTERRUPTED_BY_OWNER','process_identity':expected,'utc':datetime.now(timezone.utc).isoformat()})
    import signal,time
    os.killpg(pid,signal.SIGINT)
    # Let the bounded monitor write its final raw receipt before the unique service exits.
    for _ in range(30):
        if not Path(f'/proc/{pid}').exists():break
        time.sleep(0.5)
    else:
        if process_identity(pid)!=expected:raise GateError('PID identity changed during stop')
        os.killpg(pid,signal.SIGTERM)

    save(root/'stop-request.json',{'status':'OWNER_STOP_REQUESTED','utc':datetime.now(timezone.utc).isoformat(),
        'model_process_identity':expected,'launch_sha256':sha256(launch)})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','start','serve','stop','command'));ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--profile',choices=('slots40','c35','slots44','slots40-persistent'),default='slots40');ap.add_argument('--cap-bytes',type=int);ap.add_argument('--port',type=int,default=18440);ap.add_argument('--duration-s',type=int,default=3600);a=ap.parse_args();root=a.root.resolve()
    if a.mode=='prepare':select_profile(a.profile,a.cap_bytes);prepare(root,a.port,a.duration_s)
    elif a.mode=='start':start(root)
    elif a.mode=='stop':stop(root)
    elif a.mode=='command':print(json.dumps(monitor_command(root,verified(root)),indent=2))
    else:
        p=verified(root);rc=subprocess.call(monitor_command(root,p))
        raw=root/'raw'/f'{p["run_id"]}.json'
        save(root/'serve-receipt.json',{'status':('CLOSED_MONITORED_SESSION' if raw.is_file() else 'FAIL_HARNESS_PREMODEL'),
            'returncode':rc,'raw_sha256':sha256(raw) if raw.is_file() else None,'utc':datetime.now(timezone.utc).isoformat()})
        raise SystemExit(rc)
