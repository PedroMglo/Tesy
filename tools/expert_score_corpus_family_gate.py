"""Exact training-only corpus population, including EOS partials."""
import argparse, json
from pathlib import Path
from expert_prediction_corpus_gate import inspect

def eligibility(counts):
    if len(counts)!=8 or any(type(n) is not int or not 0<=n<=128 for n in counts):
        raise ValueError('exact eight bounded actual frame counts')
    admitted=min(counts)>=16 and sum(counts)>=512
    return {'status':'GO_FIXED_AFFINE_TRAINING_DATA' if admitted else 'NO_GO_FROZEN_TRAINING_DATA_MINIMUM',
            'admitted':admitted,'frames_by_conversation':counts,'total_frames_per_layer':sum(counts),
            'scope':'Original native auxiliary labels; not functional success, output throughput or useful latency.'}

def family(directory):
    d=Path(directory);p=json.loads((d/'protocol.json').read_text());tasks=json.loads(Path(p['training_tasks']).read_text());fixture=json.loads(Path(p['fixture']).read_text())
    runs=p['runs']
    if len(runs)!=8 or [r.get('case') for r in runs]!=[t['id'] for t in tasks] or len({r['id'] for r in runs})!=8 or len({r['command'][4] for r in runs})!=8:
        raise ValueError('exact ordered eight independent training roots/IDs')
    out=[]
    for r in runs:
        if r['env'] or r['command'][5:]!=['train128','v1'] or r['command'][2]!=p['fixture'] or r['command'][3]!=r['case']:
            raise ValueError('original training-only numerical/protocol identity')
        out.append(inspect(r['command'][4],fixture[r['case']],r['case']))
    v=eligibility([a['decode_calls'] for a in out]);v['cases']=out
    v['fit_protocol']={'official_fixture':p['fixture'],'tasks':p['training_tasks'],
                       'runs':[{'case':r['case'],'root':r['command'][4]} for r in runs]}
    return v

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=family(a.directory)
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
if __name__=='__main__':main()
