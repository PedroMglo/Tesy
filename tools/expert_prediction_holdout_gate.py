"""New task-disjoint native-prefix prediction boundary. Historical fixed32 gates unchanged."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from expert_store_cost_gate import transport
from r2_causal_gate import initial_identity
from expert_service_window_gate import FIELDS
from expert_prediction_scenario import Service,simulate
from expert_real_prediction_scenario import simulate_real

def prefix_events(path,on,n_calls):
    lines=Path(path).read_text().splitlines()
    if type(n_calls) is not int or not 0<=n_calls<=32:raise ValueError('native prefix count')
    if not lines or lines[0].split()!=FIELDS:raise ValueError('event schema')
    rows=[dict(zip(FIELDS,map(int,line.split()),strict=True)) for line in lines[1:]]
    if len(rows)>131072 or any(x['kind'] not in range(1,17) or x['us']<=0 or x['call'] not in range(n_calls+1) for x in rows):raise ValueError('event fields/bounds')
    if not on:
        if rows:raise ValueError('trace OFF unexpectedly recorded events')
        return rows
    if not rows:raise ValueError('trace ON missing')
    features={};routers={};calls={};reads={};commits={};dequeues={};demands={}
    for x in rows:
        c,l,k=x['call'],x['layer'],x['kind'];key=(c,l)
        if k==1 and c>0:
            if key in features or not 0<=l<=24 or x['rows']!=1:raise ValueError('feature missing/duplicate/shape')
            features[key]=x['us']
        if k==2 and c>0:
            if key in routers or not 0<=l<=35 or x['rows']!=1:raise ValueError('router duplicate/shape')
            routers[key]=x['us']
        if k==3 and c>0:
            if not 0<=x["expert"]<128 or x["bytes"] not in (0,1,2):raise ValueError("demand state")
            z=demands.setdefault(key,[])
            if x["expert"] in z:raise ValueError("duplicate authoritative expert")
            z.append(x["expert"])
        if k in (15,16):
            if (c,k) in calls:raise ValueError('duplicate call endpoint')
            calls[c,k]=x['us']
        if k in (5,6,7,8,9,10):
            w=(l,x['expert'],x['slot'],x['gen'])
            if not 0<=l<=35 or not 0<=x['expert']<128 or not 0<=x['slot']<40 or x['gen']<=0:raise ValueError('work key')
            if k==5:
                if w in dequeues:raise ValueError('generation loaded twice')
                dequeues[w]=x
            elif k==10:
                if w in commits:raise ValueError('duplicate commit')
                commits[w]=x
            else:
                z=(w,x['component'],k)
                if z in reads or x['component'] not in (0,1,2) or x['bytes']!=4406400:raise ValueError('component duplicate/type/size')
                reads[z]=x['us']
    if set(features)!={(c,l) for c in range(1,n_calls+1) for l in range(25)} or set(routers)!={(c,l) for c in range(1,n_calls+1) for l in range(36)}:raise ValueError('exact decode feature/router coverage')
    if set(demands)!=set(routers) or any(len(x)!=4 for x in demands.values()):raise ValueError('exact top-k demand coverage')
    if set(calls)!={(c,k) for c in range(n_calls+1) for k in (15,16)}:raise ValueError('call endpoints omitted')
    for c in range(n_calls+1):
        if calls[c,15]>=calls[c,16]:raise ValueError('call clock')
    for k,t in features.items():
        if not calls[k[0],15]<=t<=routers[k]<=calls[k[0],16]:raise ValueError('feature/router causality')
    if set(commits)!=set(dequeues):raise ValueError('uncommitted/incomplete workers')
    for w,d in dequeues.items():
        end=commits[w];last=d['us']
        if (d['call'],d['route'])!=(end['call'],end['route']):raise ValueError('worker owner changed')
        for component in range(3):
            for kind in (6,7,8,9):
                t=reads.get((w,component,kind))
                if t is None or t<last:raise ValueError('component lifecycle incomplete/unordered')
                last=t
        if last>end['us']:raise ValueError('published before native copy completion')
    return rows

def extract_prefix(rows,n_calls):
    if not 1<=n_calls<=32:raise ValueError("empty/unbounded prefix cannot receive scenario score")
    route={};feature={};begin={};end={};remap={};wait={};demands={};enqueues={};starts={};commits={};components={}
    key=lambda x:(x['layer'],x['expert'],x['slot'],x['gen'])
    for i,x in enumerate(rows):
        c,l,k,t=x['call'],x['layer'],x['kind'],x['us'];cl=c,l
        if k==15:begin[c]=t
        if k==16:end[c]=t
        if k==1:feature.setdefault(cl,[]).append(t)
        if k==2:route.setdefault(cl,[]).append(t)
        if k==14:remap[cl]=t
        if k in (11,12):wait.setdefault(cl,{})[k]=t
        if k==3:demands.setdefault(cl,[]).append(x)
        if k==4:enqueues.setdefault((c,l,x['expert']),[]).append(x)
        if k==5:starts[key(x)]=x
        if k==10:commits[key(x)]=x
        if k in (6,7,8,9):components.setdefault(key(x),{})[x['component'],k]=t
    t0=begin[1];jobs={}
    for w,x in starts.items():
        cc=components[w];read=sum(cc[k,7]-cc[k,6] for k in range(3));copy=sum(cc[k,9]-cc[k,8] for k in range(3));overhead=commits[w]['us']-x['us']-read-copy
        if overhead<0:raise ValueError('overlapping perworker phases')
        jobs[w]={'read':float(read),'copy':float(copy+overhead),'order':x['us'],'owner':x['call'],'begin':x['us'],'end':commits[w]['us']}
    groups=[];prior=t0
    for c in range(1,n_calls+1):
        for l in range(36):
            cl=c,l;rt=route[cl][0];ft=feature[cl][0] if l<=24 else rt;done=remap[cl]
            wi=wait.get(cl);stall=wi[12]-wi[11] if wi else 0
            # Everything except the observed readiness wait remains sequential fixed work.
            after=done-rt-stall
            if ft<prior or rt<ft or after<0:raise ValueError('noncausal segment decomposition')
            need=[]
            for d in demands[cl]:
                if d['bytes']==2:continue # measured RESIDENT only; LOADING is never free
                if d['bytes']==1:w=key(d)
                else:
                    es=enqueues.get((c,l,d['expert']),[])
                    if not es:raise ValueError('missing authoritative enqueue')
                    w=key(es[0])
                if w not in jobs:raise ValueError('unknown physical service')
                need.append(w)
            groups.append({'call':c,'layer':l,'pre':ft-prior,'attention':rt-ft,'after':after,'wait':stall,'need':need,'original_ready':done})
            prior=done
    tail=end[n_calls]-prior
    if tail<0:raise ValueError('tail clock')
    initial=[w for w,j in jobs.items() if j['begin']<t0<j['end']]
    late=[w for w,j in jobs.items() if j['owner']==0 and j['begin']>=t0]
    return jobs,groups,tail,float(end[n_calls]-t0),initial,late,t0


def prefix_arm(root,fixture,case,on,control_root=None):
    root=Path(root);v=json.loads((root/'result.json').read_text());ids=fixture['ids'];n=len(ids);calls=v.get('decode_calls')
    if type(calls) is not int or not 0<=calls<=32:raise ValueError('actual native call count')
    control=None
    if control_root:
        control=json.loads((Path(control_root)/'result.json').read_text())
        if initial_identity(control)!=initial_identity(v):raise ValueError('clean control initial state differs')
    prefix=n-153;plan=[min(256,prefix-pos) for pos in range(0,prefix,256)]+[153]
    expected={'status':'COMPLETE_NATIVE_PREDICTION_HELDOUT_PREFIX','profile':'R0','case':case,'official_input_ids':ids,'external_prefill_calls':plan,'decode_calls':calls,'decode_positions':[n,n+calls-1] if calls else None,'output_rows':calls+1,'vocab':201088,'FFN_last_layer_rows_per_call':1,'mode':0,'layerspan':32,'numerical_FFN_tiles':[32,32,32,32,25],'last_use_order_env':None,'initial_prefix_mode':0,'full_row_retention_bytes':(calls+1)*201088*4,'heldout':True,'training':False,'sampling_policy':'native-greedy-temp0-seed42','template_date':'2026-09-30','reasoning_effort':'medium','prefix_capture_cap':32,'trace':True,'trace_capacity':131072,'continuation_origin':'PROVIDED_NATIVE_CONTROL_PREFIX' if on else 'NATIVE_GREEDY_CONTROL_PREFIX'}
    if not 2000<=n<=2600 or any(v.get(k)!=value for k,value in expected.items()):raise ValueError('heldout input/profile/call/shape/phase identity')
    for name,size in [('official_input_ids',n),('teacher_forced_ids',calls),('native_argmax_ids',calls+1)]:
        a=v.get(name)
        if type(a) is not list or len(a)!=size or any(type(x) is not int or not 0<=x<201088 for x in a):raise ValueError('native ID sequence missing/type/count')
    if v['teacher_forced_ids']!=v['native_argmax_ids'][:calls]:raise ValueError('native control greedy prefix mapping')
    if type(v.get('terminal_eog')) is not bool or (calls<32 and not v['terminal_eog']):raise ValueError('partial observation lacks nativeEOS witness')
    expected_output=v['teacher_forced_ids']+([v['native_argmax_ids'][-1]] if v['terminal_eog'] else [])
    output=v.get('native_output_ids')
    if type(output) is not list or any(type(x) is not int or not 0<=x<201088 for x in output) or not expected_output or output!=expected_output:raise ValueError('observed output IDs/bonus/EOS cardinality')
    if control and any(v.get(k)!=control.get(k) for k in ('official_input_ids','teacher_forced_ids','native_argmax_ids','native_output_ids','terminal_eog','decode_calls')):raise ValueError('same-profile control trajectory')
    for name in ('prefix_s','prefill153_s','decode_window_s','total_s'):
        val=v.get(name)
        if type(val) not in (int,float) or not math.isfinite(val) or val<=0:raise ValueError('finite phase clock')
    if not math.isclose(v['total_s'],v['prefill153_s']+v['decode_window_s'],rel_tol=1e-10,abs_tol=1e-8):raise ValueError('phase clocks inconsistent')
    for name in ('initial','final'):
        state=v[name]
        if state.get('pending_queue')!=0 or [z.get('layer') for z in state.get('layers',[])]!=list(range(36)):raise ValueError('complete state missing')
        for layer in state['layers']:
            if any(type(layer.get(k)) is not list or len(layer[k])!=40 for k in ('slot_expert','slot_state','slot_generation','slot_claimed')) or any(layer['slot_claimed']) or any(i not in (0,2) for i in layer['slot_state']):raise ValueError('state/claims invalid')
    transport(v,'ORIGINAL')
    p=root/'all-position.logits.f32'
    if p.stat().st_size!=(calls+1)*201088*4:raise ValueError('complete logits truncated')
    logits=np.fromfile(p,dtype='<f4').reshape(calls+1,201088)
    if not np.isfinite(logits).all() or logits.argmax(axis=1).tolist()!=v['native_argmax_ids']:raise ValueError('finite full-logit/argmax evidence')
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    if control_root and h!=hashlib.sha256((Path(control_root)/'all-position.logits.f32').read_bytes()).hexdigest():raise ValueError('same-profile full-logit mismatch')
    rows=prefix_events(root/'events.tsv',True,calls)
    if v['trace_events']!=len(rows) or not 0<v['trace_bytes_reserved']<=64*2**20:raise ValueError('trace bounds')
    meta=json.loads((root/'estimator.json').read_text())
    if meta.get('enabled') is not on or meta.get('training') is not False or meta.get('decode_calls')!=calls or meta.get('schema')!='original-destination-gate-on-earlier-residual-v1' or meta.get('source_horizon')!=2 or meta.get('CPU_backend_threads')!=8 or not 0<meta.get('capture_bytes',0)<=64*2**20:raise ValueError('estimator scope/identity')
    def array(name,n):
        p=root/name
        if p.stat().st_size!=n*4:raise ValueError('capture array truncated')
        a=np.fromfile(p,dtype='<f4')
        if not np.isfinite(a).all():raise ValueError('nonfinite capture array')
        return a
    gt=array('true-routing-scores.f32',calls*23*128).reshape(calls,23,128);true={}
    for row in rows:
        if row['kind']==3 and row['call']>0 and 2<=row['layer']<=24:true.setdefault((row['call'],row['layer']),[]).append(row)
    if len(true)!=calls*23 or any(len(z)!=4 for z in true.values()):raise ValueError('true labels missing')
    for (c,l),z in true.items():
        if set(np.argsort(-gt[c-1,l-2],kind='stable')[:4].tolist())!={i['expert'] for i in z}:raise ValueError('actual true gate disagrees authoritative router')
    records=meta.get('records');cost=0.;missing=hit=issued=correct=0
    if on:
        array('earlier-input.f32',calls*23*2880);score=array('prediction-scores.f32',calls*23*128).reshape(calls,23,128)
        if [(z.get('call'),z.get('source_layer'),z.get('target_layer')) for z in records]!=[(c,l,l+2) for c in range(1,calls+1) for l in range(23)]:raise ValueError('exact actual prediction cardinality/order')
        for z in records:
            c,l=z['call'],z['target_layer'];pids=z['prediction_ids'];states=z['available_primary_state'];dt=z['complete_predictor_us']
            if pids!=np.argsort(-score[c-1,l-2],kind='stable')[:4].tolist() or len(set(pids))!=4 or len(states)!=4 or [i['expert'] for i in states]!=pids:raise ValueError('prediction score/ID/state mapping')
            if type(dt) not in (int,float) or not math.isfinite(dt) or dt<=0:raise ValueError('predictor cost clock')
            cost+=dt;absent={i['expert'] for i in true[c,l] if i['bytes']!=2}
            for i in states:
                if i['state'] not in (0,1,2) or (i['state']==0 and (i['slot']!=-1 or i['generation']!=0)) or (i['state']!=0 and (not 0<=i['slot']<40 or i['generation']<=0)):raise ValueError('forecast primary state invalid')
            forecasts={i['expert'] for i in states if i['state']==0};missing+=len(absent);hit+=len(absent&set(pids));issued+=len(forecasts);correct+=len(absent&forecasts)
    elif records or (root/'earlier-input.f32').exists() or (root/'prediction-scores.f32').exists():raise ValueError('clean control unexpectedly forecasts')
    return {'measurement_valid':True,'status':'PASS_NATIVE_HELDOUT_PREFIX' if calls>=16 else 'VALID_PARTIAL_EOS_PREFIX_NOT_COMPUTABLE_FOR_INVESTMENT','investment_window_valid':calls>=16,'case':case,'decode_calls':calls,'complete_logits_sha256':h,'miss_recall':hit/missing if missing else None,'issued_precision':correct/issued if issued else None,'missing_demands':missing if on else None,'hypothetical_issued':issued if on else None,'predictor_complete_s':cost/1e6 if on and calls else None,'native_timings':{k:v[k] for k in ('prefix_s','prefill153_s','decode_window_s','total_s')},'outcome_note':'At most32 nativegreedy input forwards for predictor data; not completefunctional response/quality success or promoted latency.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--case',required=True);p.add_argument('--on',choices=('0','1'),required=True);p.add_argument('--control',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=prefix_arm(a.root,json.loads(a.fixture.read_text())[a.case],a.case,a.on=='1',a.control)
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
if __name__=='__main__':main()
