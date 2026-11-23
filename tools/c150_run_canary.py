"""Frozen serial native mmap canary; no performance acceptance."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import c146_epoch as epoch
from c147_page_cache import census
from c149_numeric_gate import inspect, compare

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results/c150-upstream-mmap-canary-20260930T0151Z'
MODEL='/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf'
BIN=ROOT/'results/c147-file-paging-harness-20260930T0123Z/build'
BACK=ROOT/'backends/c148-upstream-mmap'

def write(name,value):
    with (R/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def inside():
    started=time.monotonic(); attempts=[];status='NUMERIC_NOT_QUALIFIED'
    env=os.environ.copy()
    for key in ('GGML_CUDA_REGISTER_HOST','LD_PRELOAD','TESY_CPU_WAVE_SKIP_PARKED'):env.pop(key,None)
    env['TESY_MMAP_NO_PREFETCH']='1'
    def run(label,command,timeout,inventory=False):
        if time.monotonic()-started+timeout+20>890:raise RuntimeError('canary envelope exhausted before subprocess')
        argv=[sys.executable,str(ROOT/'tools/run_bounded.py'),'--run-id','c150-'+label,'--model-id','gpt-oss-120b-mxfp4-gguf',
              '--backend','stock','--backend-root',str(BACK),'--output-root',str(R/'raw'),'--variant','CPU-MoE-mmap-ctx8192',
              '--workload',str(R/'protocol.json'),'--cache-condition',label,'--resource-protocol',str(R/'protocol.json'),
              '--require-telemetry','--timeout-s',str(timeout)]
        if inventory:argv+=['--collect-start-inventory']
        argv+=['--',*map(str,command)]
        result=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=timeout+(75 if inventory else 20))
        attempts.append({'label':label,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        write(label+'-attempt.json',attempts[-1])
        if result.returncode:raise RuntimeError('numeric/capacity subprocess failed: '+label)
    try:
        cache=census(MODEL)
        write('page-cache-initial.json',cache)
        if cache['active_mappings']:raise RuntimeError('conflicting active GGUF mapping')
        if not cache['unreadable_process_maps']:write('page-cache-relinquished.json',census(MODEL,relinquish=True))
        run('capacity',[BIN/'c149_mmap_boundary',MODEL,ROOT/'results/c2-target-numeric-v1.ids',R/'raw/capacity','capacity'],60,True)
        run('boundary-initial',[BIN/'c149_mmap_boundary',MODEL,ROOT/'results/c2-target-numeric-v1.ids',R/'raw/boundary-initial','boundary'],140)
        write('page-cache-retained.json',census(MODEL))
        run('boundary-retained',[BIN/'c149_mmap_boundary',MODEL,ROOT/'results/c2-target-numeric-v1.ids',R/'raw/boundary-retained','boundary'],140)
        tensors={x['name']:x for x in map(json.loads,(ROOT/'results/c148-upstream-mmap-build-20260930T0125Z/tensor-metadata.jsonl').read_text().splitlines()) if 'name' in x}
        first=inspect(R/'raw/boundary-initial',tensors);second=inspect(R/'raw/boundary-retained',tensors)
        write('boundary-summary.json',{'initial':first,'retained':second,'repeat':compare(first,second)})
        for layer in range(36):run('reference-'+str(layer),[BIN/'c149_mmap_reference',MODEL,R/'raw/boundary-initial',layer,'--ngl',12],10)
        status='CANONICAL_AND_REPEAT_NUMERIC_PASS_PREFIX_NOT_YET_QUALIFIED'
        error=None
    except Exception as exc:error=str(exc)
    write('decision.json',{'status':status,'error':error,'attempts':len(attempts),'elapsed_s':time.monotonic()-started,
          'scope':'CPU-MoE/native ctx8192/boundary189+32; no performance or prefix qualification','next_action':'prefix gate and B screen' if error is None else 'diagnose class; pivot A on material numeric/capacity failure'})
    return 0 if error is None else 1

def main():
    if '--inside' in sys.argv:return inside()
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True):raise RuntimeError('measurement tree dirty')
    lock=json.loads((ROOT/'models.lock.json').read_text())
    matches=[x for x in lock['models'] if x['id']=='gpt-oss-120b-mxfp4-gguf' and str(Path(x['path']).resolve())==MODEL]
    if len(matches)!=1 or matches[0]['sha256_verified']!='582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d':raise RuntimeError('model lock identity preflight')
    if not epoch.budget(900,600*2**20)['admitted']:raise RuntimeError('canary family not admitted')
    start=epoch.now();head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    argv=['systemd-run','--user','--slice=tesy-post-c145.slice','--unit=c150-mmap-canary','--collect','--pipe','--wait',
          '--working-directory='+str(ROOT),'-p','MemoryMax=21474836480','-p','MemoryHigh=20937965568','-p','MemorySwapMax=0',
          '-p','RuntimeMaxSec=900','-p','TimeoutStopSec=10','--',sys.executable,str(Path(__file__).resolve()),'--inside']
    result=subprocess.run(argv,text=True,capture_output=True,timeout=920);end=epoch.now()
    write('family-receipt.json',{'measurement_commit':head,'start':start,'end':end,'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    epoch.record('c149-native-mmap-canary',start,end,live=True,status='PASS' if result.returncode==0 else 'FAIL_OR_NOT_QUALIFIED',paths=[R/'family-receipt.json'],worst_case_s=900)
    print(json.dumps({'returncode':result.returncode,'decision':str(R/'decision.json'),'elapsed_s':end['monotonic_s']-start['monotonic_s']}))
    return result.returncode
if __name__=='__main__':raise SystemExit(main())
