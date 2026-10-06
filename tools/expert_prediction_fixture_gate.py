"""Official vocabulary-only heldout fixture, no output/feature/model training."""
import argparse,hashlib,json,struct
from pathlib import Path

def validate(fixture,tasks):
    if list(fixture)!=[x['id'] for x in tasks] or len(tasks)!=2 or len(set(fixture))!=2:raise ValueError('exact unique ordered two tasks')
    out=[]
    for task in tasks:
        v=fixture[task['id']];ids=v.get('ids')
        if type(ids) is not list or not 2000<=len(ids)<=2600 or any(type(x) is not int or not 0<=x<201088 for x in ids):raise ValueError('official2K input IDs absent/type/count')
        if v.get('task')!=task or v.get('template_date')!='2026-09-30' or v.get('reasoning_effort')!='medium' or v.get('weights_loaded') is not False or v.get('forwards')!=0:raise ValueError('task/template/metadata-only scope')
        prompt=v.get('rendered_prompt')
        if type(prompt) is not str or not prompt or '2026-09-30' not in prompt or 'Reasoning: medium' not in prompt:raise ValueError('native rendered template missing')
        out.append({'id':task['id'],'official_input_count':len(ids),'prefix_count':len(ids)-153,'warm_new_count':153,'input_ids_int32le_sha256':hashlib.sha256(struct.pack('<'+str(len(ids))+'i',*ids)).hexdigest(),'prompt_utf8_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    return {'status':'PASS_OFFICIAL_HELDOUT_VOCAB_ONLY','cases':out,'weights_loaded':False,'forwards':0,'scope':'Predictor task-disjointheldout prefix tasks, not final quality/utililty qualification; coretext/data fixed before any modelanswer'}

def main():
    p=argparse.ArgumentParser();p.add_argument('fixture',type=Path);p.add_argument('--tasks',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=validate(json.loads(a.fixture.read_text()),json.loads(a.tasks.read_text()))
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
if __name__=='__main__':main()
