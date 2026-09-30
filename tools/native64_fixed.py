"""Four fixed-input timing arms; monitored C109-derived probe, no server replay."""
import argparse,csv,json,os,subprocess,time,struct,math
from pathlib import Path
from native64_numeric import read,save,git,verify_run,MODEL,BACKEND,CAP
from run_bounded import sha256,relevant_environment
from epoch_accounting import Epoch,now
from native64_evaluate import evaluate
ORDER=('A32','B64','B64','A32')

def run(root):
    p=read(root/'protocol.json');epoch=Epoch(p['epoch']);phase=now();measurement=git('rev-parse','HEAD');rows=[];reason=None;status='FAIL_OR_INCOMPLETE_EVIDENCE'
    if git('status','--porcelain') or relevant_environment(os.environ):raise ValueError('fixed-input measurement not clean')
    if not epoch.budget(750,32*2**20)['admitted']:raise ValueError('W whole unit not admitted')
    phase_deadline=time.monotonic()+750
    try:
        for order,arm in enumerate(ORDER):
            rid=f'c192-w{order+1}-{arm}';start=now();stem=root/'raw'/rid;model_output=str(stem)+'.probe'
            remain=min(180,phase_deadline-time.monotonic())
            if remain<180:raise ValueError('complete next W arm does not fit frozen phase')
            if sha256(p['identity']['binaries']['fixed'])!=p['identity']['binary_sha256']['fixed'] or sha256(root/'inputs.tsv')!=p['input_sha256']:raise ValueError('W binary/inputs changed')
            cmd=['python3','tools/run_bounded.py','--run-id',rid,'--model-id','gpt-oss-120b-mxfp4-gguf','--backend','streaming','--backend-root',str(BACKEND),'--output-root',str((root/'raw').resolve()),'--variant','C75-slots40-'+arm,'--workload',str((root/'inputs.tsv').resolve()),'--cache-condition','fresh-pools-fixed-prefix-transcript-page-cache-uncontrolled','--timeout-s','110','--resource-protocol',str((root/'protocol.json').resolve()),'--require-telemetry','--collect-start-inventory','--env','TESY_CPU_WAVE_SKIP_PARKED=1','--',p['identity']['binaries']['fixed'],str(MODEL),str((root/'inputs.tsv').resolve()),model_output,'--arm',arm]
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            if proc.returncode:raise ValueError('W monitor failed '+proc.stderr[-900:])
            m=verify_run(stem,p,'fixed',{'TESY_CPU_WAVE_SKIP_PARKED':'1'})
            if m['workload_sha256']!=p['input_sha256']:raise ValueError('executed workload SHA changed')
            with open(model_output+'.calls.tsv') as f:calls=list(csv.DictReader(f,delimiter='\t'))
            expected_calls=[(i*256,n,i*256+n-1,2043) for i,n in enumerate([256]*7+[252])]+[(2044,153,2196,2196)]+[(2197+i,1,2197+i,2197+i) for i in range(32)]
            if [(int(x['first_abs']),int(x['n_tokens']),int(x['last_abs']),int(x['output_abs'])) for x in calls]!=expected_calls:raise ValueError('executed prefix/warm/decode call plan changed')
            with open(model_output+'.ops.tsv') as f:ops=list(csv.DictReader(f,delimiter='\t'))
            with open(model_output+'.steps.tsv') as f:steps=list(csv.DictReader(f,delimiter='\t'))
            if len(ops)!=1 or ops[0]['arm']!=arm or ops[0]['prompt_tokens']!='2197' or ops[0]['continuation_tokens']!='32' or ops[0]['logit_rows']!='3' or len(steps)!=32:raise ValueError('fixed execution counts changed')
            expected=read(root/'inputs.json')['continuation32']
            if any((int(r['step']),int(r['position']),int(r['token_id']))!=(i,2197+i,expected[i]) for i,r in enumerate(steps)):raise ValueError('fixed forwards positions/IDs changed')
            data=Path(model_output+'.logits.f32').read_bytes()
            if len(data)!=3*201088*4 or any(not math.isfinite(x) for (x,) in struct.iter_unpack('<f',data)):raise ValueError('selected logits truncated/nonfinite')
            row={'run_id':rid,'profile':arm,'complete':True,'natural':True,'identity':True,'resources':True,'deadline':True,'samples':True,'input_sha256':p['input_sha256'],'schedule_sha256':p['schedule_sha256'],'prefill153_s':float(ops[0]['prefill_s']),'decode32_s':float(ops[0]['decode_s']),'prefix_prepare_s':float(ops[0]['prefix_prepare_s']),'model_load_s':float(ops[0]['model_load_s']),'context_init_s':float(ops[0]['context_init_s']),'maxima':m['maxima'],'start':start,'end':now(),'measurement_head':measurement,'manifest_sha256':sha256(str(stem)+'.json'),'selected_logits_sha256':sha256(model_output+'.logits.f32'),'equal_input_not_equal_routing':True}
            if row['end']['monotonic_s']-start['monotonic_s']>180:raise ValueError('W arm total deadline')
            save(root/(rid+'-receipt.json'),row);rows.append(row);print(json.dumps({'arm':arm,'prefill153_s':row['prefill153_s'],'decode32_s':row['decode32_s'],'prefix_prepare_s':row['prefix_prepare_s']}),flush=True)
        result=evaluate([(rows[0],rows[1]),(rows[3],rows[2])],'W');status=result['status']
        save(root/'paired-metrics.json',result)
    except Exception as exc:reason=type(exc).__name__+': '+str(exc)
    finally:
        end=now();epoch.record('c192-W-fixed-input',phase,end,live=True,status=status,paths=[root/'decision.json'],worst_case_s=750)
        save(root/'decision.json',{'status':'NO_GO_NATIVE64_FIXED_INPUT_SCREEN' if status=='NO_GO_W_SCREEN' else status,'reason':reason,'measurement_head':measurement,'arms':rows,'start':phase,'end':end,'claim':'Equal official input IDs/external call plan; native arithmetic/routing/cache state can differ; no user first-final or generated throughput claim','S':'ADMITTED_IF_W_GO' if status=='GO_W_SCREEN' else 'NOT_RUN_W_GATE','publication':'LOCAL_ONLY'})
        save(root/'budget-checkpoint.json',epoch.budget())
    print(status,reason,flush=True);return 0 if status=='GO_W_SCREEN' else 1
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('root',type=Path);v=a.parse_args();raise SystemExit(run(v.root))
