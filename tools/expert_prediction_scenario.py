"""Scoped optimistic byte anticipation; fixed observed demand stream and service sensitivity.
Not a realizable predictor, cache policy replay, physical traffic or universal roofline.
Uses existing strict trace/evidence gates and union algebra, no snapshot framework.
"""
import argparse,heapq,json,statistics
from pathlib import Path
from expert_service_window_gate import events
from c122_trace_validate import union_us

WEIGHT_BYTES=13219200

class Service:
    def __init__(self,jobs,scale,arena):
        self.jobs={key:dict(j,state='NEW',demand=False,stage=False) for key,j in jobs.items()}
        self.scale=scale;self.arena=arena//WEIGHT_BYTES;self.staged=0;self.peak=0;self.running=[];self.queue=[];self.serial=0;self.now=0.;self.wasted=0
    def request(self,key,demand):
        j=self.jobs[key]
        if demand:j['demand']=True
        if j['state']=='NEW':j['state']='QUEUED';j['stage']=not demand;self.queue.append(key)
        elif j['state']=='READY' and demand:j['state']='COPY_QUEUED';self.queue.append(key)
        self.dispatch()
    def dispatch(self):
        while len(self.running)<4:
            eligible=[k for k in self.queue if self.jobs[k]['demand'] or not self.jobs[k]['stage'] or self.staged<self.arena]
            if not eligible:return
            key=min(eligible,key=lambda k:(not self.jobs[k]['demand'],self.jobs[k]['order']))
            self.queue.remove(key);j=self.jobs[key]
            if j['state']=='COPY_QUEUED':part='COPY';dt=j['copy']
            elif j['stage']:
                part='READ';dt=j['read'];self.staged+=1;self.peak=max(self.peak,self.staged)
            else:part='FULL';dt=j['read']+j['copy']
            j['state']='RUN_'+part;self.serial+=1
            heapq.heappush(self.running,(self.now+dt*self.scale,self.serial,key,part))
    def advance(self,t):
        if t<self.now-1e-9:raise ValueError('time reversed')
        while self.running and self.running[0][0]<=t:
            self.now,_,key,part=heapq.heappop(self.running);j=self.jobs[key]
            if part=='READ':
                j['state']='READY'
                if j['demand']:j['state']='COPY_QUEUED';self.queue.append(key)
            else:
                j['state']='DONE'
                if j['stage']:self.staged-=1
            self.dispatch()
        self.now=t;self.dispatch()
    def wait(self,keys):
        while any(self.jobs[k]['state']!='DONE' for k in keys):
            if not self.running:raise ValueError('queue stalled or arena insufficient')
            self.advance(self.running[0][0])


def extract(rows):
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
    for c in range(1,33):
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
    tail=end[32]-prior
    if tail<0:raise ValueError('tail clock')
    initial=[w for w,j in jobs.items() if j['begin']<t0<j['end']]
    late=[w for w,j in jobs.items() if j['owner']==0 and j['begin']>=t0]
    return jobs,groups,tail,float(end[32]-t0),initial,late,t0


def simulate(data,horizon,scale,arena):
    jobs,groups,tail,observed,initial,late,t0=data;s=Service(jobs,scale,arena)
    # Outstanding warm-prefill bytes are neither empty cache nor free readiness.
    for w in initial:
        j=s.jobs[w];j.update(state='RUN_FULL',demand=True,stage=False);s.serial+=1
        heapq.heappush(s.running,(max(0.,j['end']-t0)*scale,s.serial,w,'FULL'))
    for w in late:s.request(w,True)
    by={(g['call'],g['layer']):g for g in groups}
    for g in groups:
        s.advance(s.now+g['pre'])
        if horizon is not None and g['layer']<=24:
            target=g['layer']+horizon
            if target<=24:
                for w in by[g['call'],target]['need']:s.request(w,False)
        s.advance(s.now+g['attention'])
        for w in g['need']:s.request(w,True)
        s.wait(g['need'])
        s.advance(s.now+g['after'])
    s.advance(s.now+tail)
    return {'decode_us':s.now,'staging_peak_bytes':s.peak*WEIGHT_BYTES,'staging_capacity_bytes':arena,'observed_decode_us':observed,'original_decode_wait_us':sum(g['wait'] for g in groups),'initial_inflight':len(initial)+len(late)}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();protocol=json.loads((a.directory/'protocol.json').read_text());out={'schema':'optimistic-activation-byte-scenario-v1','classification':'OPTIMISTIC_OFFLINE_SCENARIO','assumptions':['Observed original missing-demand/generation stream held fixed; no new cache hits/evictions awarded','Same original three-read service and native copies; predictorzero/falsepositiveszero; staging reads before truth, destinationcopy only after true demand','Four nonpreemptible whole-expert worker tasks; demand priority,128MiB arena includes running/ready stages; no future token forecasting','Nonwait attention/compute/sampling gaps fixed; feature release recomputed as earlier readiness waits accelerate','Observed service duration fixed ONLY conditioned scenario; sensitivity0.8/1.0/1.2; physical bandwidth/cache/contention can change','No transfer of slots44 timing or logicalbytes into physicalNVMe claims'], 'cases':{}}
    for case in ('nominal153','code153'):
        reports=[]
        for run in protocol['runs']:
            if run['case']!=case or not run['trace']:continue
            data=extract(events(Path(run['command'][4])/'events.tsv',True));observed=data[3];report={'run':run['id'],'service_sensitivity':[]}
            for scale in (.8,1.,1.2):
                baseline=simulate(data,None,scale,128*2**20);variants={}
                for horizon in (0,2):
                    v=simulate(data,horizon,scale,128*2**20);v['gain_vs_same_service_replay_percent']=100*(baseline['decode_us']-v['decode_us'])/baseline['decode_us'];variants[str(horizon)]=v
                report['service_sensitivity'].append({'scale':scale,'baseline':baseline,'baseline_vs_observed_percent':100*(baseline['decode_us']-observed)/observed,'variants':variants})
            reports.append(report)
        out['cases'][case]=reports
    out['scope']='CPU same-layer and CPU two-layers-earlier only; fixed supplied153+32 inputs and observed residency, not learned predictor, generatedtoken or realizable production benefit.'
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
if __name__=='__main__':main()
