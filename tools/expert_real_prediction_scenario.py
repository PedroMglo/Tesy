"""Development-only conditional service scenario with actual predictor costs and false reads.
Observed services/cache demand stream fixed; no physical latency or promotion claim.
"""
import heapq, statistics
from expert_prediction_scenario import Service, WEIGHT_BYTES

class PredictedService(Service):
    def __init__(self,jobs,scale,arena):
        super().__init__(jobs,scale,arena); self.reads=0;self.expired_reads=0
    def cancel(self,key):
        j=self.jobs[key]
        if j['demand'] or j['state']=='DONE':return
        if j['state']=='QUEUED':self.queue.remove(key);j['state']='CANCELLED'
        elif j['state']=='READY':self.staged-=1;j['state']='CANCELLED';self.expired_reads+=1
        elif j['state']=='RUN_READ':j['expired']=True
        elif j['state']=='NEW':j['state']='CANCELLED'
        self.dispatch()
    def advance(self,t):
        if t<self.now-1e-9:raise ValueError('time reversed')
        while self.running and self.running[0][0]<=t:
            self.now,_,key,part=heapq.heappop(self.running);j=self.jobs[key]
            if part=='READ':
                self.reads+=1
                if j.get('expired') and not j['demand']:
                    j['state']='CANCELLED';self.staged-=1;self.expired_reads+=1
                else:
                    j['state']='READY'
                    if j['demand']:j['state']='COPY_QUEUED';self.queue.append(key)
            else:
                j['state']='DONE'
                if j['stage']:self.staged-=1
            self.dispatch()
        self.now=t;self.dispatch()


def simulate_real(data,records,scale=1.,arena=128*2**20):
    jobs,groups,tail,observed,initial,late,t0=data
    by={(g['call'],g['layer']):g for g in groups}
    predictions={};cost={};cancel={};augmented={k:dict(j) for k,j in jobs.items()}
    for x in records:
        source=(x['call'],x['source_layer']);target=(x['call'],x['target_layer'])
        if source in predictions or target not in by:raise ValueError('duplicate or out-of-scope prediction')
        if x['target_layer']!=x['source_layer']+2:raise ValueError('unexpected horizon')
        keys=[];needed={w[1]:w for w in by[target]['need']}
        for state in x['available_primary_state']:
            if state['state']!=0:continue # observed RESIDENT/LOADING bypass; no free LOADING
            expert=state['expert']
            if expert in needed:key=needed[expert]
            else:
                key=('false',x['call'],x['target_layer'],expert)
                services=[j['read'] for w,j in jobs.items() if w[0]==x['target_layer']]
                if not services:raise ValueError('no measured wrong-expert read reference')
                augmented[key]={'read':statistics.median(services),'copy':0.,'order':1e12+len(augmented)}
            keys.append(key)
        predictions[source]=keys;cost[source]=x['complete_predictor_us'];cancel[target]=keys
    s=PredictedService(augmented,scale,arena)
    for w in initial:
        j=s.jobs[w];j.update(state='RUN_FULL',demand=True,stage=False);s.serial+=1
        heapq.heappush(s.running,(max(0.,j['end']-t0)*scale,s.serial,w,'FULL'))
    for w in late:s.request(w,True)
    for g in groups:
        key=g['call'],g['layer'];s.advance(s.now+g['pre'])
        if key in predictions:
            s.advance(s.now+cost[key])
            for w in predictions[key]:s.request(w,False)
        s.advance(s.now+g['attention'])
        for w in g['need']:s.request(w,True)
        for w in cancel.get(key,[]):s.cancel(w) # expire wrong predictions at actual target router
        s.wait(g['need']);s.advance(s.now+g['after'])
    s.advance(s.now+tail)
    return {'decode_us':s.now,'predictor_complete_us':sum(cost.values()),'staging_peak_bytes':s.peak*WEIGHT_BYTES,'read_completed':s.reads,'expired_read_completed':s.expired_reads,'queued_expirations_avoid_read':sum(j['state']=='CANCELLED' and not j.get('expired') for j in s.jobs.values()),'scope':'Development-only fixed observed missing-generation stream and compute, original OFF trace; actual predictor timings; false reads use target-layer measured median with service sensitivity. No speculation gain measured; primary cache held fixed; stage lookup/mutex service overhead not yet measured.'}


def main():
    import argparse,json,hashlib
    import numpy as np
    from pathlib import Path
    from expert_service_window_gate import events
    from expert_prediction_scenario import extract,simulate
    from expert_activation_gate import inspect_estimator
    from r2_causal_gate import init_identity
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    protocol=json.loads((a.directory/'protocol.json').read_text());r0=a.directory.parents[1]
    fixture_path=r0/'results/c276-post-c274-r2-causal-qualification-20261005T204839Z/development-inputs.json'
    fixture=json.loads(fixture_path.read_text());out={'status':'DEVELOPMENT_CONDITIONAL_REAL_PREDICTION_SCENARIO','classification':'ESTIMADO','training':False,'staged_bytes_in_actual_model':0,'holdout':False,'cases':{},'assumptions':['Actual OFF trace services/work and observed missing-generation stream fixed, primary cache not resimulated','ON measured complete predictor duration and emitted top4 used, not oracle future IDs for issuing','False read durations use observed destination-layer median, service sensitivity0.8/1/1.2; no zero-cost false positives','Four nonpreemptible workers, demand priority and128MiB includes running/ready staged bytes','Wrong prediction expires at true router; running read cannot be undone and delays demands; destination copy only after truth','Stage lookup/staging-copy/coordination integration overhead still unmeasured; development scenario does not satisfy heldoutcanary gate']}
    for case in ('nominal153','code153'):
        runs=[x for x in protocol['runs'] if x.get('case')==case];off,on=runs
        offroot=Path(off['command'][4]);onroot=Path(on['command'][4]);expected=protocol['expected_full_logits_sha256'][case]
        offv=inspect_estimator(offroot,fixture[case],case,False,expected);onv=inspect_estimator(onroot,fixture[case],case,True,expected)
        if init_identity(json.loads((offroot/'initial.json').read_text()))!=init_identity(json.loads((onroot/'initial.json').read_text())):raise ValueError('estimator control initial state differs')
        rows=events(offroot/'events.tsv',True);data=extract(rows)
        labels=np.fromfile(onroot/'true-routing-scores.f32',dtype='<f4').reshape(32,23,128)
        true={}
        for e in events(onroot/'events.tsv',True):
            if e['kind']==3 and e['call']>0 and 2<=e['layer']<=24:true.setdefault((e['call'],e['layer']),set()).add(e['expert'])
        for (c,l),ids in true.items():
            if set(np.argsort(-labels[c-1,l-2],kind='stable')[:4].tolist())!=ids:raise ValueError('true original biased-score labels disagree with authoritative selected IDs')
        records=json.loads((onroot/'estimator.json').read_text())['records'];sens=[]
        for scale in (.8,1.,1.2):
            b=simulate(data,None,scale,128*2**20);v=simulate_real(data,records,scale,128*2**20)
            v['gain_percent']=100*(b['decode_us']-v['decode_us'])/b['decode_us'];sens.append({'service_scale':scale,'baseline':b,'prediction':v})
        out['cases'][case]={'capture_analysis':onv,'control':offv,'sensitivity':sens,'raw':{'control':str(offroot),'estimator':str(onroot)}}
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print({c:v['sensitivity'][1]['prediction']['gain_percent'] for c,v in out['cases'].items()})
if __name__=='__main__':main()
