"""Conditional fixed-service scenario with the observed C305 worker semantics.

Includes native primary consumers occupying a worker while a stage producer reads.
It is not a physical bandwidth simulator or a measured integrated improvement.
"""
import heapq,statistics
from expert_prediction_scenario import WEIGHT_BYTES

class NativeStageService:
    def __init__(self,jobs,scale,arena):
        self.jobs={k:dict(j,primary='NEW',stage='NONE',expired=False,attached=False) for k,j in jobs.items()}
        self.scale=scale;self.capacity=arena//WEIGHT_BYTES;self.occupied=0;self.peak=0
        self.now=0.;self.serial=0;self.issue=0;self.running=[];self.blocked=set();self.demands=[];self.forecasts=[]
        self.reads=0;self.expired_reads=0;self.no_capacity=0;self.blocked_worker_us=0.

    def push(self,key,role,dt):
        self.serial+=1;heapq.heappush(self.running,(self.now+dt*self.scale,self.serial,key,role))

    def release(self,key):
        j=self.jobs[key]
        if j['stage']=='NONE':raise ValueError('stage double release')
        self.occupied-=1;j['stage']='NONE'

    def request(self,key,demand):
        j=self.jobs[key]
        if demand:
            if j['primary']=='NEW':j['primary']='QUEUED';self.demands.append(key)
        elif j['primary']=='NEW' and j['stage']=='NONE':
            if self.occupied>=self.capacity:self.no_capacity+=1;return
            self.issue+=1;j.update(stage='QUEUED',ticket=self.issue);self.forecasts.append(key)
            self.occupied+=1;self.peak=max(self.peak,self.occupied)
        self.dispatch()

    def dispatch(self):
        while len(self.running)+len(self.blocked)<4:
            if self.demands:
                key=min(self.demands,key=lambda k:self.jobs[k]['order']);self.demands.remove(key);j=self.jobs[key]
                if j['stage']=='QUEUED':
                    self.forecasts.remove(key);self.release(key) # native queued-stage fallback
                if j['stage']=='READING':
                    j.update(primary='BLOCKED',attached=True,blocked_since=self.now);self.blocked.add(key)
                elif j['stage']=='READY':
                    j.update(primary='RUN_COPY',stage='CONSUMING',attached=True);self.push(key,'COPY',j['copy'])
                else:
                    if j['stage']!='NONE':raise ValueError('native primary state invalid')
                    j['primary']='RUN_FULL';self.push(key,'FULL',j['read']+j['copy'])
                continue
            unconfirmed=sum(role=='READ' and not self.jobs[k]['attached'] for _,_,k,role in self.running)
            if unconfirmed>=3 or not self.forecasts:return
            key=min(self.forecasts,key=lambda k:self.jobs[k]['ticket']);self.forecasts.remove(key)
            j=self.jobs[key];j['stage']='READING';self.push(key,'READ',j['read'])

    def cancel(self,key):
        j=self.jobs[key]
        if j['primary']!='NEW' or j['stage']=='NONE':return
        if j['stage']=='QUEUED':self.forecasts.remove(key);self.release(key)
        elif j['stage']=='READY':self.expired_reads+=1;self.release(key)
        elif j['stage']=='READING':j['expired']=True
        else:raise ValueError('unknown stage cancellation')
        self.dispatch()

    def advance(self,t):
        if t<self.now-1e-9:raise ValueError('native service time reversed')
        while self.running and self.running[0][0]<=t:
            self.now,_,key,role=heapq.heappop(self.running);j=self.jobs[key]
            if role=='READ':
                self.reads+=1
                if j['expired'] and j['primary']=='NEW':self.expired_reads+=1;self.release(key)
                elif key in self.blocked:
                    self.blocked.remove(key);self.blocked_worker_us+=self.now-j['blocked_since']
                    j.update(primary='RUN_COPY',stage='CONSUMING');self.push(key,'COPY',j['copy'])
                else:j['stage']='READY'
            else:
                j['primary']='DONE'
                if role=='COPY':self.release(key)
            self.dispatch()
        self.now=t;self.dispatch()

    def wait(self,keys):
        while any(self.jobs[k]['primary']!='DONE' for k in keys):
            if not self.running:raise ValueError('native queue deadlock')
            self.advance(self.running[0][0])

    def finish(self):
        for key in self.jobs:self.cancel(key)
        while any(j['stage']!='NONE' for j in self.jobs.values()):
            if not self.running:raise ValueError('native stage finish stalled')
            self.advance(self.running[0][0])

def simulate_native(data,records,scale=1.,arena=128*2**20):
    jobs,groups,tail,observed,initial,late,t0=data;by={(g['call'],g['layer']):g for g in groups}
    predicted={};cost={};cancel={};augmented={k:dict(v) for k,v in jobs.items()}
    for r in records:
        source=r['call'],r['source_layer'];target=r['call'],r['target_layer']
        if source in predicted or target not in by or target[1]!=source[1]+2:raise ValueError('exact native forecast horizon/cardinality')
        need={k[1]:k for k in by[target]['need']};keys=[]
        for state in r['available_primary_state']:
            if state['state']!=0:continue
            expert=state['expert']
            if expert in need:key=need[expert]
            else:
                key=('false',target[0],target[1],expert)
                reference=[j['read'] for k,j in jobs.items() if k[0]==target[1]]
                if not reference:raise ValueError('no actual false-read layer service')
                augmented[key]={'read':statistics.median(reference),'copy':0.,'order':1e12+len(augmented)}
            keys.append(key)
        predicted[source]=keys;cost[source]=r['complete_predictor_us'];cancel[target]=keys
    s=NativeStageService(augmented,scale,arena)
    for key in initial:
        j=s.jobs[key];j['primary']='RUN_FULL';s.push(key,'FULL',max(0.,j['end']-t0))
    for key in late:s.request(key,True)
    for g in groups:
        key=g['call'],g['layer'];s.advance(s.now+g['pre'])
        if key in predicted:
            s.advance(s.now+cost[key])
            for k in predicted[key]:s.request(k,False)
        s.advance(s.now+g['attention'])
        for k in g['need']:s.request(k,True)
        for k in cancel.get(key,[]):s.cancel(k)
        s.wait(g['need']);s.advance(s.now+g['after'])
    s.advance(s.now+tail);before=s.now;s.finish()
    return {'decode_us':s.now,'predictor_complete_us':sum(cost.values()),'staging_peak_bytes':s.peak*WEIGHT_BYTES,
            'read_completed':s.reads,'expired_read_completed':s.expired_reads,'capacity_rejections':s.no_capacity,
            'stage_finish_us':s.now-before,'blocked_primary_worker_us':s.blocked_worker_us,
            'scope':'Fixed observed original primary demands/cache and IO/copy services; four workers, queued-stage fallback, ten arena entries, at most3 unconfirmed reads, actual wait-on-producer worker occupancy and finish. Native isolated predictor costs included. Actual contention/mutex/cache and changed service durations remain unknown.'}
