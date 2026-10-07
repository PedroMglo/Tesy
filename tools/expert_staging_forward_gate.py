"""Selected real forward links for staging, without fictitious demand-read events."""
import argparse,json
from pathlib import Path
import numpy as np
from expert_staging_gate import arm
from expert_service_window_gate import FIELDS

def links(root,on):
    root=Path(root);lines=(root/'events.tsv').read_text().splitlines()
    if not lines or lines[0].split()!=FIELDS:raise ValueError('real native event schema absent')
    events=[dict(zip(FIELDS,map(int,x.split()),strict=True)) for x in lines[1:]]
    if not 0<len(events)<=131072:raise ValueError('actual native bounded events missing')
    true={};features={};calls={};enqueues={};dequeues={};commits={};copy={};reads={}
    for e in events:
        k,c,l=e['kind'],e['call'],e['layer']
        if not 1<=k<=16 or e['us']<=0 or not 0<=c<=32:raise ValueError('native event kind/clock/scope')
        if k==1 and c>0:
            if (c,l) in features or not 0<=l<=24 or e['rows']!=1:raise ValueError('early feature duplicate/device/shape')
            features[c,l]=e['us']
        if k==3 and c>0:
            a=true.setdefault((c,l),[])
            if not 0<=e['expert']<128 or e['expert'] in a or e['bytes'] not in (0,1,2):raise ValueError('true routing IDs/state invalid')
            a.append(e['expert'])
        if k in (15,16):
            if (c,k) in calls:raise ValueError('duplicate native call endpoint')
            calls[c,k]=e['us']
        if k in (4,5,6,7,8,9,10):
            w=(c,l,e['expert'],e['slot'],e['gen'])
            if not 0<=l<=35 or not 0<=e['expert']<128 or not 0<=e['slot']<40 or e['gen']<=0:raise ValueError('authoritative primary work key')
            if k==4:enqueues[w]=e
            elif k in (5,10):
                table=dequeues if k==5 else commits
                if w in table:raise ValueError('duplicate native claimed/RESIDENT generation')
                table[w]=e
            else:
                if e['component'] not in (0,1,2) or e['bytes']!=4406400:raise ValueError('native component identity')
                key=(w,e['component'],k);table=copy if k in (8,9) else reads
                if key in table:raise ValueError('duplicate native component event')
                table[key]=e['us']
    if set(features)!={(c,l) for c in range(1,33) for l in range(25)} or set(true)!={(c,l) for c in range(1,33) for l in range(36)} or any(len(a)!=4 for a in true.values()) or set(calls)!={(c,k) for c in range(33) for k in (15,16)}:raise ValueError('real feature/topk/call coverage incomplete')
    if set(dequeues)!=set(commits) or not set(dequeues)<=set(enqueues):raise ValueError('primary worker pending/receipt incomplete')
    stage=json.loads((root/'staging.json').read_text());staged={}
    for e in stage['journal']:
        if e['kind']==11:
            w=(e['call'],e['layer'],e['expert'],e['slot'],e['generation'])
            if w in staged or w not in commits:raise ValueError('stage commit not linked to authoritative primary completion')
            staged[w]=e
        if e['kind']==1:
            if e['us']<features[e['call'],e['layer']-2]:raise ValueError('prediction issue before actual early feature')
    if not on and staged:raise ValueError('OFF actually consumed staged bytes')
    for w,begin in dequeues.items():
        end=commits[w];last=begin['us']
        for component in range(3):
            if w not in staged:
                for k in (6,7):
                    if (w,component,k) not in reads or reads[w,component,k]<last:raise ValueError('actual direct-demand read lifecycle omitted')
                    last=reads[w,component,k]
            else:
                if any((w,component,k) in reads for k in (6,7)):raise ValueError('stage hit also claims a demand disk read')
            for k in (8,9):
                if (w,component,k) not in copy or copy[w,component,k]<last:raise ValueError('native destination copy lifecycle omitted')
                last=copy[w,component,k]
        if last>end['us']:raise ValueError('RESIDENT published before destination complete')
    # Predictor and true routing are independently observed arrays; future labels
    # never enter the movement callback. Stable ranking is checked here offline.
    labels=np.fromfile(root/'true-routing-scores.f32',dtype='<f4').reshape(32,23,128)
    for c in range(1,33):
        for l in range(2,25):
            if set(np.argsort(-labels[c-1,l-2],kind='stable')[:4].tolist())!=set(true[c,l]):raise ValueError('original biased true scores disagree with routed expert IDs')
    if on:
        predictions=np.fromfile(root/'prediction-scores.f32',dtype='<f4').reshape(32,23,128)
        for e in json.loads((root/'estimator.json').read_text())['records']:
            if e['prediction_ids']!=np.argsort(-predictions[e['call']-1,e['target_layer']-2],kind='stable')[:4].tolist():raise ValueError('captured native movement scores differ from issued top4')
    return {'native_event_count':len(events),'actual_staged_primary_commits':len(staged),'all_real_primary_commits':len(commits),'true_router_labels_checked':32*23}

def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--case',required=True);p.add_argument('--on',choices=('0','1'),required=True);p.add_argument('--expected',required=True);p.add_argument('--witness',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args();on=a.on=='1'
 v=arm(a.root,json.loads(a.fixture.read_text())[a.case],a.case,on,a.expected,a.witness);v.update(links(a.root,on))
 with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
 print(v['status'])
if __name__=='__main__':main()
