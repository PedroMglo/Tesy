"""One frozen serial family using the existing bounded scope/inventory/monitor path."""
import argparse,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
from epoch_accounting import Epoch,now
from run_bounded import sha256,file_identity

def publish(path,data):
    path=Path(path);tmp=Path(str(path)+'.partial')
    with tmp.open('x') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.link(tmp,path);tmp.unlink()

def preflight(root,p):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',p['execution_scope_unit']):
        raise RuntimeError('scope must be an unsuffixed unit name; entrypoint adds .service')
    if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True):raise RuntimeError('measurement tree dirty')
    if file_identity(Path(p['model_path']))!=p['model_stat']:raise RuntimeError('model stat changed')
    lock=json.loads((root/'models.lock.json').read_text())
    matches=[x for x in lock['models'] if x['id']==p['model_id'] and Path(x['path']).resolve()==Path(p['model_path']).resolve() and x['sha256_verified']==p['model_sha256_previously_verified']]
    if len(matches)!=1:raise RuntimeError('model lock mismatch')
    for path,h in p['file_sha256'].items():
        if sha256(Path(path))!=h:raise RuntimeError('frozen file hash changed: '+path)
    if subprocess.check_output(['git','-C',p['backend_root'],'rev-parse','HEAD'],text=True).strip()!=p['backend_commit'] or subprocess.check_output(['git','-C',p['backend_root'],'status','--porcelain'],text=True):raise RuntimeError('backend source changed')

def post_timeout(run):
    value=run.get('post_run_timeout_s',90)
    if type(value) not in (int,float) or not 0<value<=90:
        raise ValueError('post-run timeout must be finite and in (0,90]')
    return value

def server_run(directory,p,run_id):
    from types import SimpleNamespace
    import c2_server_run as server
    from c9_server_admission import validate_receipt
    from run_bounded import inventory_before_spawn
    from c118_start_inventory import require_inventory
    from datetime import datetime
    run=next(r for r in p['runs'] if r['id']==run_id)
    spec=run['server'];protocol_path=Path(spec['protocol']);arm=json.loads(protocol_path.read_text())
    config=json.loads(Path(spec['config']).read_text());tasks=json.loads(Path(spec['tasks']).read_text())
    inventory_before_spawn(directory,run_id,arm)
    code=server.run(SimpleNamespace(run_id=run_id,protocol=protocol_path,suite='native-prefix',model='target120b'),arm,config,[(r['id'],r) for r in tasks],Path(spec['model_path']))
    if code:return code
    raw=json.loads((directory/'raw'/(run_id+'.json')).read_text())
    samples=[json.loads(x) for x in (directory/'raw'/(run_id+'.samples.jsonl')).read_text().splitlines()]
    validate_receipt(arm,config,raw,samples,directory,run_id=run_id,protocol_filename=str(protocol_path),expected_results=len(tasks))
    receipt=json.loads((directory/'raw'/(run_id+'.start-inventory.receipt.json')).read_text())
    launch=json.loads((directory/'raw'/(run_id+'.launch.json')).read_text())
    if launch['start_inventory']['receipt_sha256']!=sha256(directory/'raw'/(run_id+'.start-inventory.receipt.json')):raise RuntimeError('launch inventory hash')
    policy=json.loads((directory/'resource-policy.json').read_text())
    require_inventory(directory,run_id,receipt,policy=policy,cap_bytes=arm['resources']['cgroup']['memory_max_bytes'],expected_power={k:policy['power'][k] for k in ('source','profile')},duration_s=60,now=datetime.fromisoformat(launch['start_inventory']['popen_invoked_utc']),max_age_s=3)
    return 0

def inside(root,directory,p):
    started=time.monotonic();attempts=[];status='FAIL_HARNESS_PREMODEL';error=None
    try:
        for run in p['runs']:
            needed=run['timeout_s']+(65 if run['inventory'] else 0)+15+(post_timeout(run) if run.get('post_run_command') else 0)
            if time.monotonic()-started+needed>p['physical_envelope_s']-5:raise RuntimeError('envelope before next launch exhausted')
            env={k:v for k,v in os.environ.items() if not k.startswith(('LLAMA_','TESY_','GGML_','CUDA_')) and k not in ('LD_PRELOAD','LD_LIBRARY_PATH')}
            env.update(p['common_env']);env.update(run['env'])
            cmd=[sys.executable,str(root/'tools/run_bounded.py'),'--run-id',run['id'],'--model-id','model-free' if run.get('model_free') else p['model_id'],'--backend','stock','--backend-root',p['backend_root'],'--output-root',str(directory/'raw'),'--variant',run['variant'],'--workload',str(directory/'protocol.json'),'--cache-condition',run['label'],'--resource-protocol',str(directory/'protocol.json'),'--require-telemetry','--timeout-s',str(run['timeout_s'])]
            if run['inventory']:cmd+=['--collect-start-inventory']
            cmd+=['--',*run['command']]
            if run.get('server'):
                cmd=[sys.executable,str(root/'tools/residency_unit_run.py'),str(directory),'--server-run',run['id']]
            a=now();r=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=needed);b=now()
            row={'id':run['id'],'start':a,'end':b,'argv':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr};attempts.append(row);publish(directory/(run['id']+'-attempt.json'),row)
            if r.returncode:raise RuntimeError('bounded subprocess failed: '+run['id'])
            if run.get('post_run_command'):
                gate=subprocess.run(run['post_run_command'],cwd=root,text=True,capture_output=True,timeout=post_timeout(run))
                publish(directory/(run['id']+'-gate.json'),{'returncode':gate.returncode,'stdout':gate.stdout,'stderr':gate.stderr})
                if gate.returncode:raise RuntimeError('post-run correctness gate failed: '+run['id'])
        if p.get('analysis_command'):
            r=subprocess.run(p['analysis_command'],cwd=root,text=True,capture_output=True,timeout=90)
            publish(directory/'analysis-attempt.json',{'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
            if r.returncode:raise RuntimeError('numeric/evidence analysis failed')
        status=p['success_status']
    except Exception as exc:error=str(exc)
    publish(directory/'decision.json',{'status':status if error is None else 'FAIL_UNIT_PRESERVED','error':error,'attempts':len(attempts),'elapsed_s':time.monotonic()-started,'scope':p['claim_scope']})
    return 0 if error is None else 1

def main():
    a=argparse.ArgumentParser();a.add_argument('directory',type=Path);a.add_argument('--inside',action='store_true');a.add_argument('--server-run');args=a.parse_args()
    directory=args.directory.resolve();root=directory.parents[1];p=json.loads((directory/'protocol.json').read_text())
    if args.server_run:return server_run(directory,p,args.server_run)
    if args.inside:return inside(root,directory,p)
    epoch=Epoch(root/p['epoch_path']);head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    start=now();result=None;live_started=False
    try:
        preflight(root,p)
        if not epoch.budget(p['physical_envelope_s'],p['raw_projection_bytes'])['admitted']:raise RuntimeError('unit and closure not admitted')
        c=p['resources']['cgroup'];deadline=epoch.config['start_monotonic_s']+epoch.config['wall_limit_s'];runtime=min(p['physical_envelope_s'],int(deadline-time.monotonic()))
        argv=['systemd-run','--user','--slice=tesy-post-c154.slice','--unit='+p['execution_scope_unit'],'--collect','--pipe','--wait','--working-directory='+str(root),'-p','MemoryMax='+str(c['memory_max_bytes']),'-p','MemoryHigh='+str(c['memory_high_bytes']),'-p','MemorySwapMax=0','-p','RuntimeMaxSec='+str(runtime),'-p','TimeoutStopSec=10','--',sys.executable,str(Path(__file__).resolve()),str(directory),'--inside']
        live_started=True
        result=subprocess.run(argv,text=True,capture_output=True,timeout=runtime+15);end=now()
        publish(directory/'family-receipt.json',{'measurement_commit':head,'start':start,'end':end,'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        epoch.record(p['campaign_id'],start,end,live=True,status='PASS' if result.returncode==0 else 'FAIL_UNIT',paths=[directory/'family-receipt.json'],worst_case_s=p['physical_envelope_s'])
    except Exception as exc:
        if live_started:
            subprocess.run(['systemctl','--user','stop',p['execution_scope_unit']],capture_output=True,timeout=15)
        end=now();publish(directory/'premodel-receipt.json',{'measurement_commit':head,'start':start,'end':end,'status':'FAIL_UNIT' if live_started else 'FAIL_HARNESS_PREMODEL','error':str(exc)})
        epoch.record(p['campaign_id'],start,end,live=live_started,status='FAIL_UNIT' if live_started else 'FAIL_HARNESS_PREMODEL',paths=[directory/'premodel-receipt.json'])
        raise
    print(json.dumps({'returncode':result.returncode,'decision':str(directory/'decision.json'),'elapsed_s':end['monotonic_s']-start['monotonic_s']}));return result.returncode
if __name__=='__main__':raise SystemExit(main())
