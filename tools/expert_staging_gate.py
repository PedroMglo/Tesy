"""C305 prospective staging byte/lifetime boundary; historical gates unchanged."""
import argparse,json,math
from pathlib import Path
import numpy as np
from r2_causal_gate import inspect,METRICS

def demand_stats(v):
    keys=['issued','deduplicated','no_capacity','reads','completed_reads','logical_read_weight_bytes','expired_queued','expired_ready','expired_running','consumed','waits','errors','peak_running_spec','validation_claims','validation_components']
    s=v.get('stats',{})
    if set(s)!=set(keys) or any(type(x) is not int or x<0 for x in s.values()):raise ValueError('staging counters absent/type')
    if s['errors'] or s['reads']!=s['completed_reads'] or s['logical_read_weight_bytes']!=s['reads']*13219200 or s['peak_running_spec']>3 or s['consumed']>s['reads'] or s['validation_components']!=3*s['validation_claims'] or s['validation_claims']>8:raise ValueError('staging completion/resource/byte counters')
    return s

def validate_journal(meta, predictions, witness):
    if meta.get('idle') is not True or meta.get('fd_O_DIRECT') is not True or meta.get('DIO_memory_alignment',0)<=0 or meta.get('DIO_offset_alignment',0)<=0:raise ValueError('staging byte mode/lifetime absent')
    if not 0<meta.get('arena_bytes',0)+meta.get('metadata_bytes',0)<=128*2**20:raise ValueError('arena128MiB accounting')
    stats=demand_stats(meta);events=meta.get('journal')
    if type(events) is not list or len(events)>24576 or meta.get('journal_capacity')!=24576:raise ValueError('journal cardinality')
    tickets={};last_us=0;kind_counts={};active=set()
    for ev in events:
        if set(ev)!={'us','scope','ticket','generation','kind','call','layer','expert','slot','component'} or any(type(x) is not int for x in ev.values()):raise ValueError('journal event schema')
        if ev['us']<last_us or ev['scope']!=1 or ev['ticket']<=0 or not 1<=ev['call']<=32 or not 2<=ev['layer']<=24 or not 0<=ev['expert']<128:raise ValueError('journal timestamp/scope/key')
        last_us=ev['us'];t=ev['ticket'];k=ev['kind'];kind_counts[k]=kind_counts.get(k,0)+1
        key=ev['call'],ev['layer'],ev['expert']
        if k==1:
            if t in tickets or key not in predictions or len(active)>=10:raise ValueError('issued future/duplicate/unbounded forecast')
            tickets[t]={'key':key,'state':'QUEUED','demand':False,'validated':set(),'commit':False};active.add(t)
        else:
            if t not in active or tickets[t]['key']!=key:raise ValueError('stale stage event ownership')
            v=tickets[t];state=v['state']
            if k==2:
                if state!='QUEUED':raise ValueError('read dispatched without queued bytes')
                v['state']='READING'
                if sum(x['state']=='READING' and not x['demand'] for i,x in tickets.items() if i in active)>3:raise ValueError('demand worker reserve lost')
            elif k==3:
                if state!='READING':raise ValueError('read completion before actual dispatch')
                v['state']='READY'
            elif k==4:
                if state not in ('QUEUED','READY') or v['demand']:raise ValueError('expiry freed running/consumer data')
                active.remove(t)
            elif k==5:
                if state!='READING' or v['demand']:raise ValueError('expiry wrong lifetime')
                v['expired']=True
            elif k==6:
                if state not in ('READING','READY') or v.get('expired') or v['demand']:raise ValueError('invalid authoritative attachment')
                v['demand']=True
            elif k==7:
                if state!='READY' or not v['demand'] or not 0<=ev['slot']<40 or ev['generation']<=0:raise ValueError('consumer before correct byte completion')
                v['state']='CONSUMING';v['slot']=ev['slot'];v['generation']=ev['generation']
            elif k in (10,11):
                if state!='CONSUMING' or ev['slot']!=v['slot'] or ev['generation']!=v['generation']:raise ValueError('wrong primary slot/generation witness or commit')
                if k==10:
                    if ev['component'] not in (0,1,2) or ev['component'] in v['validated']:raise ValueError('canonical witness component duplicate')
                    v['validated'].add(ev['component'])
                else:
                    if v['commit']:raise ValueError('duplicate primary RESIDENT commit')
                    v['commit']=True
            elif k==8:
                if state!='CONSUMING' or not v['commit']:raise ValueError('consumer release before owned RESIDENT commit')
                active.remove(t)
            else:raise ValueError('read error/unknown journal kind')
    if active:raise ValueError('staging partial/cleanup absent')
    if any(kind_counts.get(k,0)!=stats[name] for k,name in ((1,'issued'),(2,'reads'),(3,'completed_reads'),(8,'consumed'),(10,'validation_components'),(11,'consumed'))):raise ValueError('journal/counter receipt mismatch')
    if witness and (stats['validation_claims']!=8 or stats['consumed']<8):raise ValueError('actual canonical consumer witness not exercised')
    if not meta.get('enabled') and (events or any(stats.values())):raise ValueError('OFF speculative work present')
    if meta.get('enabled') and not (stats['issued']>0 and stats['reads']>0 and stats['consumed']>0):raise ValueError('candidate staging not actually consumed')
    return {'stats':stats,'journal_events':len(events),'consumed_with_complete_canonical_witness':stats['validation_claims']}

def arm(root,fixture,case,on,expected,witness=False):
    root=Path(root);v,h=inspect(root,fixture,'R0',case)
    if h!=expected:raise ValueError('same-profile full33 logits differ from original R0 reference')
    if v.get('staging_enabled') is not on or v.get('estimator_enabled') is not on or v.get('diagnostic_byte_witness') is not witness:raise ValueError('production/diagnostic stage toggle contract')
    for key in ('decode_forward_s','stage_cleanup_s'):
        x=v.get(key)
        if type(x) not in (int,float) or not math.isfinite(x) or x<0:raise ValueError('stage phase timing absent/invalid')
    if not math.isclose(v['decode32_s'],v['decode_forward_s']+v['stage_cleanup_s'],abs_tol=1e-8):raise ValueError('pending read cleanup excluded from cost')
    estimate=json.loads((root/'estimator.json').read_text());records=estimate.get('records');predictions=set()
    if estimate.get('enabled') is not on or estimate.get('training') is not False or estimate.get('source_horizon')!=2 or estimate.get('CPU_backend_threads')!=8:raise ValueError('actual estimator identity')
    if on:
        if [(x.get('call'),x.get('source_layer'),x.get('target_layer')) for x in records]!=[(c,l,l+2) for c in range(1,33) for l in range(23)]:raise ValueError('prediction coverage/causality absent')
        for name,n in [('earlier-input.f32',32*23*2880),('prediction-scores.f32',32*23*128),('true-routing-scores.f32',32*23*128)]:
            p=root/name
            if p.stat().st_size!=n*4 or not np.isfinite(np.fromfile(p,dtype='<f4')).all():raise ValueError('feature/label evidence truncated/nonfinite')
        for r in records:
            ids=r['prediction_ids'];dt=r['complete_predictor_us']
            if len(ids)!=4 or len(set(ids))!=4 or any(type(x) is not int or not 0<=x<128 for x in ids) or type(dt) not in (int,float) or not math.isfinite(dt) or dt<=0:raise ValueError('predictor IDs/cost invalid')
            states=r['available_primary_state']
            if len(states)!=4 or [x['expert'] for x in states]!=ids:raise ValueError('prediction primary state keys')
            for x in states:
                if x['state'] not in (0,1,2):raise ValueError('primary LOADING unknown')
                if x['state']==0:predictions.add((r['call'],r['target_layer'],x['expert']))
    elif records:raise ValueError('OFF predictions unexpectedly executed')
    stage=json.loads((root/'staging.json').read_text())
    if stage.get('enabled') is not on:raise ValueError('stage receipt toggle differs')
    audit=validate_journal(stage,predictions,witness)
    return {'status':'PASS_SELECTED_R0_CPU_STAGING_FIDELITY','case':case,'stage':on,'witness':witness,'full33_logits_sha256':h,'metrics':{k:v[k] for k in METRICS},'decode_forward_s':v['decode_forward_s'],'stage_cleanup_s':v['stage_cleanup_s'],**audit,'scope':'Original full33 R0 selected same-profile rows/IDs. Real stage reads linked to primary slot/expert/generation; provided IDs are not confirmed throughput. Diagnostic witness timings are not promotion measurements.'}

def native_fixture(path):
    v=json.loads(Path(path).read_text())
    if v.get("status")!="PASS_NATIVE_STAGE_BYTES_QUEUE_WORKER_LIFETIME" or v.get("full_model_loaded") is not False or v.get("original_weight_slices_read") is not True or v.get("transformer_forwards")!=0 or v.get("fd_O_DIRECT") is not True:raise ValueError("actual slice/worker fixture identity")
    if [(x["layer"],x["expert"],x["components"],x["logical_bytes"]) for x in v.get("slice_checks",[])]!=[(2,0,3,13219200),(13,63,3,13219200),(24,127,3,13219200)]:raise ValueError("exact selected canonical byte coverage")
    if v.get("worker")!={"delivered_expert":7,"primary_slot":0,"primary_generation":1,"native_workers":4,"consumed":1,"priority_verified":True} or not 0<v.get("arena_bytes",0)+v.get("metadata_bytes",0)<=128*2**20:raise ValueError("actual worker/arena lifecycle proof")
    return {"status":"PASS_ACTUAL_NATIVE_SLICE_WORKER_BOUNDARY","scope":"Original9selectedMXFP4components, native4worker authoritativecommit/cancellation/join. No Transformer forward, timing or model-wide exactness claim.","receipt":v}

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--case');p.add_argument('--on',choices=('0','1'));p.add_argument('--expected');p.add_argument('--witness',action='store_true');p.add_argument('--native-fixture',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=native_fixture(a.root) if a.native_fixture else arm(a.root,json.loads(a.fixture.read_text())[a.case],a.case,a.on=='1',a.expected,a.witness)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])
if __name__=='__main__':main()
