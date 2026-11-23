"""One frozen C143 restoration unit; existing inventory/guard/HTTP/lifecycle paths."""
import json,sys,time,subprocess,os
from pathlib import Path
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'tools'))
from epoch_accounting import Epoch,now
import c143_slots40_optin as launcher
import optin_integration_client as client
from run_bounded import sha256,process_identity
OUT=Path(__file__).resolve().parent
EPOCH=Epoch(REPO/'results/c276-post-c274-r2-causal-qualification-20261005T204839Z')
SESSION=EPOCH.path/'raw/c281-session'

def save(name,value):
    with (OUT/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

if __name__=='__main__':
    budget=EPOCH.budget(worst_case_s=650,raw_projection=64*2**20);save('budget-before.json',budget)
    if not budget['admitted']:raise RuntimeError('NOT_RUN_BUDGET')
    start=now();failure=None;result=None;cleanup=None;preset=None
    try:
        launcher.select_profile('slots40-persistent',20*2**30)
        launcher.prepare(SESSION,18442,480)
        preset=launcher.verified(SESSION)
        save('command.json',{'monitor_command':launcher.monitor_command(SESSION,preset),'measurement_head':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),'session':str(SESSION)})
        launcher.start(SESSION)
        result=client.run(SESSION,OUT/'protocol.json')
        if result['status']!='CLIENT_TWO_REQUESTS_PASS':raise RuntimeError(result['failure'])
    except BaseException as exc:
        failure=f'{type(exc).__name__}:{exc}'
    finally:
        try:
            if preset is not None and (SESSION/'start-request.json').exists():
                unit=preset['run_id']+'.service'
                active=subprocess.check_output(['systemctl','--user','show',unit,'-p','ActiveState','--value'],text=True).strip()
                if active in ('active','activating'):
                    launcher.stop(SESSION)
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    active=subprocess.check_output(['systemctl','--user','show',unit,'-p','ActiveState','--value'],text=True).strip()
                    if active not in ('active','activating','deactivating'):break
                    time.sleep(.5)
                cleanup={'unit':unit,'active_state':active,'scope':'only own frozen PID/startticks/cgroup through C143.stop'}
                if active in ('active','activating','deactivating'):raise RuntimeError('own service did not close')
            else:cleanup={'status':'NO_OWN_MODEL_STARTED'}
        except BaseException as exc:
            cleanup={'failure':f'{type(exc).__name__}:{exc}'}
            failure=failure or cleanup['failure']
        end=now()
        if end['monotonic_s']-start['monotonic_s']>650:failure=failure or 'COMPLETE_ENVELOPE_DEADLINE'
        receipt={'start':start,'end':end,'elapsed_s':end['monotonic_s']-start['monotonic_s'],'status':'R0_PERSISTENT_LAUNCHER_TWO_REQUEST_PASS' if failure is None else 'FAIL_RESTORATION_PRESERVED','failure':failure,'cleanup':cleanup,'client_status':result['status'] if result else None,'raw_root':str(SESSION),'profile':'R0 slots40/ub32; span/order/GOMP absent; C269 imported numerical libraries unchanged','scope':'two-request actual-history launcher readiness, not new quality/M4 or performance qualification'}
        save('unit-receipt.json',receipt);EPOCH.record('C281-R0-launcher-restoration',start,end,live=True,status=receipt['status'],paths=[OUT/'unit-receipt.json'],worst_case_s=650)
        with (EPOCH.path/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps({'unit':'C281-R0-launcher-restoration','start':start,'end':end,'wall_s':receipt['elapsed_s'],'physical_s':receipt['elapsed_s'],'subset_of_global_ledger':True})+'\n')
        print(json.dumps(receipt));sys.exit(0 if failure is None else 1)
