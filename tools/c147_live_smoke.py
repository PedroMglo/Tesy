"""Run the frozen existing monitor in its own FILE_PAGING scope without weights."""
import json
from pathlib import Path
import subprocess
import sys
import c146_epoch as epoch
from run_bounded import sha256
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results/c147b-file-paging-smoke-20260930T0134Z'
def main():
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True):raise RuntimeError('measurement tree dirty')
    if not epoch.budget(80)['admitted']:raise RuntimeError('smoke envelope not admitted')
    head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    start=epoch.now()
    cmd=['systemd-run','--user','--slice=tesy-post-c145.slice','--unit=c147b-file-paging-smoke','--collect','--pipe','--wait',
        '--working-directory='+str(ROOT),'-p','MemoryMax=21474836480','-p','MemoryHigh=20937965568','-p','MemorySwapMax=0',
        '-p','RuntimeMaxSec=80','-p','TimeoutStopSec=10','--',sys.executable,str(ROOT/'tools/run_bounded.py'),
        '--run-id','c147b-live-dummy','--model-id','model-free','--backend','stock','--backend-root',str(ROOT/'backends/c148-upstream-mmap'),
        '--output-root',str(R/'raw'),'--variant','FILE_PAGING-no-model','--workload',str(R/'protocol.json'),
        '--cache-condition','no-model','--resource-protocol',str(R/'protocol.json'),'--require-telemetry',
        '--collect-start-inventory','--timeout-s','10','--',str(ROOT/'results/c147-file-paging-harness-20260930T0123Z/build/c147_dummy')]
    result=subprocess.run(cmd,text=True,capture_output=True,timeout=90);end=epoch.now()
    row={'measurement_commit':head,'start':start,'end':end,'argv':cmd,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
         'monitor_receipt_path':str(R/'raw/c147b-live-dummy.json'),'status':'PASS' if result.returncode==0 else 'FAIL_HARNESS_PREMODEL'}
    path=R/'live-smoke.json'
    with path.open('x') as f:json.dump(row,f,indent=2);f.write('\n')
    epoch.record('c147b-live-spawn-smoke',start,end,live=True,status=row['status'],paths=[path],worst_case_s=80)
    print(json.dumps(row,indent=2));return result.returncode
if __name__=='__main__':raise SystemExit(main())
