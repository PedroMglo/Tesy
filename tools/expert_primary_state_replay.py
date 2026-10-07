"""Narrow original trace metadata replay; does not simulate cache victims."""
import copy

class PrimaryState:
    def __init__(self,initial,events):
        if [l['layer'] for l in initial['layers']]!=list(range(36)):raise ValueError('all original layers required')
        self.layers=[]
        for l in initial['layers']:
            if any(len(l[k])!=40 for k in ('slot_expert','slot_state','slot_generation')):raise ValueError('complete original primary pool')
            self.layers.append([list(z) for z in zip(l['slot_expert'],l['slot_state'],l['slot_generation'])])
        self.updates=sorted((copy.copy(x) for x in events if x['kind'] in (4,10)),key=lambda x:x['us'])
        self.index=0;self.time=0

    def advance(self,t):
        if t<self.time:raise ValueError('primary replay time reversed')
        self.time=t
        while self.index<len(self.updates) and self.updates[self.index]['us']<=t:
            x=self.updates[self.index];l,s=x['layer'],x['slot']
            if not 0<=l<36 or not 0<=s<40 or not 0<=x['expert']<128 or x['gen']<=0:raise ValueError('original primary work identity')
            old=self.layers[l][s]
            if x['kind']==4:
                if x['gen']<old[2] or (x['gen']==old[2] and (old[0]!=x['expert'] or old[1]!=1)):raise ValueError('stale original reserve event')
                self.layers[l][s]=[x['expert'],1,x['gen']]
            else:
                if old!=[x['expert'],1,x['gen']]:raise ValueError('original commit missing correct loading generation')
                self.layers[l][s]=[x['expert'],2,x['gen']]
            self.index+=1

    def selected(self,layer,experts):
        out=[]
        for expert in experts:
            matches=[{'expert':a,'slot':i,'state':b,'generation':g} for i,(a,b,g) in enumerate(self.layers[layer]) if a==expert]
            if len(matches)>1:raise ValueError('duplicate original expert mapping')
            out.append(matches[0] if matches else {'expert':expert,'slot':-1,'state':0,'generation':0})
        return out

    def final(self,final):
        self.advance(max([self.time]+[x['us'] for x in self.updates]))
        expected=[[list(z) for z in zip(l['slot_expert'],l['slot_state'],l['slot_generation'])] for l in final['layers']]
        if self.layers!=expected:raise ValueError('original final metadata replay mismatch')
