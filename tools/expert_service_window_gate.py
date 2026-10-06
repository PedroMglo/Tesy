"""Bounded readiness evidence and observer qualification, not prediction benefit."""
import argparse,json,statistics
from pathlib import Path
from r2_causal_gate import inspect,initial_identity,METRICS
from expert_store_cost_gate import transport
FIELDS='kind us call route layer expert slot gen component bytes rows'.split()

def events(path,on):
    lines=Path(path).read_text().splitlines()
    if not lines or lines[0].split()!=FIELDS:raise ValueError('event schema')
    rows=[dict(zip(FIELDS,map(int,line.split()),strict=True)) for line in lines[1:]]
    if len(rows)>131072 or any(x['kind'] not in range(1,17) or x['us']<=0 or x['call'] not in range(33) for x in rows):raise ValueError('event fields/bounds')
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
    if set(features)!={(c,l) for c in range(1,33) for l in range(25)} or set(routers)!={(c,l) for c in range(1,33) for l in range(36)}:raise ValueError('exact decode feature/router coverage')
    if set(demands)!=set(routers) or any(len(x)!=4 for x in demands.values()):raise ValueError('exact top-k demand coverage')
    if set(calls)!={(c,k) for c in range(33) for k in (15,16)}:raise ValueError('call endpoints omitted')
    for c in range(33):
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

def arm(directory,fixture,case,on,expected):
    v,h=inspect(directory,fixture,'R0',case);transport(v,'ORIGINAL')
    if h!=expected or v.get('trace') is not on:raise ValueError('same-profile logits or observer toggle')
    rows=events(Path(directory)/'events.tsv',on)
    if v.get('trace_events')!=len(rows) or v.get('trace_capacity')!=131072 or not 0<v.get('trace_bytes_reserved',0)<=64*2**20:raise ValueError('bounded observer accounting')
    return v,h,rows

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--fixture',type=Path);p.add_argument('--case');p.add_argument('--on',choices=('0','1'));p.add_argument('--expected');p.add_argument('--family',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.family:
        protocol=json.loads((a.directory/'protocol.json').read_text());runs=protocol['runs']
        if len(runs)!=8 or len({x['id'] for x in runs})!=8 or [(x['case'],x['trace']) for x in runs]!=[(c,on) for c in ('nominal153','code153') for on in (False,True,True,False)]:raise ValueError('ordered unique exact two-case ABBA')
        rows={};hashes={}
        for x in runs:
            cmd=x['command'];fixture=json.loads(Path(cmd[2]).read_text())[x['case']]
            v,h,_=arm(cmd[4],fixture,x['case'],x['trace'],protocol['expected_full_logits_sha256'][x['case']]);rows.setdefault(x['case'],[]).append(v);hashes.setdefault(x['case'],[]).append(h)
        out={'status':'PASS_SELECTED_READINESS_EVIDENCE','cases':{},'full33_logits_sha256':hashes}
        for c,group in rows.items():
            overhead=[]
            for ai,bi in ((0,1),(3,2)):
                x,y=group[ai],group[bi]
                if initial_identity(x)!=initial_identity(y):raise ValueError('initial complete state differs')
                overhead.append({k:100*(y[k]-x[k])/x[k] for k in METRICS})
            med={k:statistics.median(x[k] for x in overhead) for k in METRICS}
            out['cases'][c]={'overhead_percent_by_pair':overhead,'median_overhead_percent':med,'neutral_timing':all(med[k]<=3 for k in ('prefill153_s','decode32_s')),'interpretation':'Diagnostic only + preserved trace OFF production companion if phase median overhead >3%; no constant subtraction'}
    else:
        fixture=json.loads(a.fixture.read_text())[a.case];v,h,rows=arm(a.directory,fixture,a.case,a.on=='1',a.expected)
        out={'status':'PASS_SELECTED_WINDOW_ARM','full33_logits_sha256':h,'events':len(rows),'trace':v['trace']}
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])
if __name__=='__main__':main()
