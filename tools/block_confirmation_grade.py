"""Two prospective unobserved functional classes; reuse the isolated tester."""
import ast
import json
from pathlib import Path
from c2_gate import strict_json
from grade_tasks import isolated_python,SENTINEL

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'workloads/c236_confirmation_fixtures.json'


def job_oracle(events):
    # Independent selection by job and maximum (sequence,input position),
    # followed by a distinct aggregation, not the submitted implementation.
    jobs=sorted({x['job'] for x in events});active=[]
    for job in jobs:
        position,event=max(((p,x) for p,x in enumerate(events) if x['job']==job),key=lambda pair:(pair[1]['seq'],pair[0]))
        if event['state']=='active':active.append(event)
    return [(team,sum(x['team']==team for x in active),sum((x['minutes'] or 0) for x in active if x['team']==team)) for team in sorted({x['team'] for x in active})]


def allocation_oracle(data):
    remaining=dict(data['capacities']);assignments=[];waiting=[]
    for item,priority,weight in sorted(data['items'],key=lambda x:(-x[1],x[0])):
        fit=sorted(((capacity,b) for b,capacity in remaining.items() if capacity>=weight))
        if not fit:waiting.append(item);continue
        _,bin_id=fit[0];remaining[bin_id]-=weight;assignments.append({'id':item,'bin':bin_id})
    return {'assignments':sorted(assignments,key=lambda x:x['id']),'remaining':remaining,'waiting':sorted(waiting)}


def fixture():
    data=strict_json(FIXTURE.read_text())
    if data['schema']!='c236-confirmation-functional-fixtures-v1' or len(data['job_cases'])!=9:
        raise ValueError('wrong frozen confirmation fixture')
    for case in data['job_cases']:
        if [list(x) for x in job_oracle(case['events'])]!=case['expected']:raise ValueError('independent job oracle/fixture disagree')
    if allocation_oracle(data['bin_data'])!=data['bin_expected']:raise ValueError('independent allocation oracle/fixture disagree')
    return data


def code_envelope(content):
    text=content.strip()
    if text.startswith('```python\n') and text.endswith('\n```') and text.count('```')==2:text=text[10:-4]
    if '```' in text:raise ValueError('only pure function or one whole Python fence accepted')
    try:tree=ast.parse(text)
    except SyntaxError as e:raise ValueError('invalid Python final') from e
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef) or tree.body[0].name!='job_totals' or tree.body[0].decorator_list:
        raise ValueError('exactly one undecorated job_totals function required')
    return text


def grade(task_id,content,finish_reason='stop'):
    if finish_reason!='stop' or not isinstance(content,str) or not content.strip():return {'status':'FAIL','reason':'no complete natural final'}
    data=fixture()
    if task_id=='confirm-json-bin-allocation':
        try:actual=strict_json(content)
        except (TypeError,ValueError) as e:return {'status':'FAIL','reason':'invalid whole JSON: '+str(e)}
        shape=isinstance(actual,dict) and set(actual)=={'assignments','remaining','waiting'} and isinstance(actual['remaining'],dict) and set(actual['remaining'])=={'A','B','C'} and all(type(x)is int for x in actual['remaining'].values())
        return {'status':'PASS' if shape and actual==data['bin_expected'] else 'FAIL','reason':None if shape and actual==data['bin_expected'] else 'wrong allocation/types/ordering'}
    if task_id!='confirm-code-job-totals':raise ValueError('unknown new confirmation task')
    try:code=code_envelope(content)
    except ValueError as e:return {'status':'FAIL','reason':str(e)}
    harness="import copy\nns={}\nexec(compile(open('/tmp/candidate.py').read(),'/tmp/candidate.py','exec'),ns)\nfn=ns['job_totals']\n"
    for case in data['job_cases']:
        harness+='events='+repr(case['events'])+'\nbefore=copy.deepcopy(events)\n'
        harness+='actual=fn(events)\nassert type(actual)is list and all(type(x)is tuple and len(x)==3 and type(x[0])is str and type(x[1])is int and type(x[2])is int for x in actual)\nassert actual=='+repr([tuple(x) for x in case['expected']])+', actual\nassert events==before\n'
    harness+=f'print({SENTINEL!r})\n'
    try:result=isolated_python(code,harness,'candidate.py')
    except OSError as e:return {'status':'VALIDATOR_ENV_ERROR','reason':str(e)}
    if 'bwrap:' in result.get('stderr_tail','') and 'Operation not permitted' in result['stderr_tail']:
        return {'status':'VALIDATOR_ENV_ERROR','reason':result['stderr_tail'][-300:]}
    return result
