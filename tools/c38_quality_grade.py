#!/usr/bin/env python3
"""Frozen validators for the new, synthetic C38 functional tasks."""

import json
from pathlib import Path

from c2_gate import strict_json
from grade_tasks import SENTINEL, isolated_python, unwrap


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / 'workloads/c38_quality12.json'

CODE_TESTS = {
    'c38-code-01': "assert merge_halfopen([])==[]\nassert merge_halfopen([(5,7),(1,3),(3,5),(9,9),(10,8)])==[(1,7)]\nassert merge_halfopen([(3,4),(-2,0),(1,2)])==[(-2,0),(1,2),(3,4)]\na=[(4,6),(1,2)]; merge_halfopen(a); assert a==[(4,6),(1,2)]",
    'c38-code-02': "assert latest_by_key([])=={}\na=[{'key':'x','time':2,'seq':1,'value':'old'},{'key':'y','time':5,'seq':1,'value':0},{'key':'x','time':2,'seq':3,'value':'new'},{'key':'x','time':1,'seq':99,'value':'wrong'}]; assert latest_by_key(a)=={'x':'new','y':0}; assert a[0]['value']=='old'\nassert latest_by_key([{'key':'k','time':-1,'seq':0,'value':None}])=={'k':None}",
    'c38-code-03': "assert topo_batches([],[])==[]\nassert topo_batches(['d','c','b','a'],[('a','c'),('b','c'),('c','d'),('a','c')])==[['a','b'],['c'],['d']]\nassert topo_batches(['x','y','z'],[])==[['x','y','z']]\nassert topo_batches(['a','b'],[('a','b'),('b','a')])==[]",
    'c38-code-04': "assert rolling_valid_sum([1,2,3],2)==[3,5]\nassert rolling_valid_sum([1,None,3,4],2)==[None,None,7]\nassert rolling_valid_sum([True,2,3],2)==[None,5]\nassert rolling_valid_sum([1,2],3)==[]\nassert rolling_valid_sum([],1)==[]",
}

CODE_GOLD = {
    'c38-code-01': "def merge_halfopen(intervals):\n out=[]\n for a,b in sorted((a,b) for a,b in intervals if b>a):\n  if out and a<=out[-1][1]: out[-1]=(out[-1][0],max(out[-1][1],b))\n  else: out.append((a,b))\n return out",
    'c38-code-02': "def latest_by_key(records):\n found={}\n for r in records:\n  k=r['key']; rank=(r['time'],r['seq'])\n  if k not in found or rank>found[k][0]: found[k]=(rank,r['value'])\n return {k:v for k,(_,v) in found.items()}",
    'c38-code-03': "def topo_batches(nodes,edges):\n adj={n:set() for n in nodes}; deg={n:0 for n in nodes}\n for a,b in edges:\n  if b not in adj[a]: adj[a].add(b);deg[b]+=1\n out=[];seen=0\n while seen<len(nodes):\n  batch=sorted(n for n in nodes if deg[n]==0)\n  if not batch:return []\n  out.append(batch);seen+=len(batch)\n  for n in batch:\n   deg[n]=-1\n   for q in adj[n]:deg[q]-=1\n return out",
    'c38-code-04': "def rolling_valid_sum(xs,width):\n return [sum(w) if all(type(x) is int for x in w) else None for i in range(len(xs)-width+1) for w in [xs[i:i+width]]]",
}

CODE_MUTANT = {
    'c38-code-01': 'def merge_halfopen(intervals): return sorted(intervals)',
    'c38-code-02': "def latest_by_key(records): return {r['key']:r['value'] for r in records}",
    'c38-code-03': 'def topo_batches(nodes,edges): return [sorted(nodes)] if nodes else []',
    'c38-code-04': 'def rolling_valid_sum(xs,width): return [sum(xs[i:i+width]) for i in range(len(xs)-width+1)]',
}

SQL_CASES = {
    'c38-sql-01': [
        ("CREATE TABLE users(id,name); CREATE TABLE sessions(id,user_id,minutes,state); INSERT INTO users VALUES(1,'a'),(2,'b'),(3,'c'); INSERT INTO sessions VALUES(1,1,7,'complete'),(2,1,99,'open'),(3,2,NULL,'complete'),(4,2,4,'complete');", [[1,7],[2,4],[3,0]]),
        ("CREATE TABLE users(id,name); CREATE TABLE sessions(id,user_id,minutes,state); INSERT INTO users VALUES(8,'x'),(4,'y'); INSERT INTO sessions VALUES(1,8,0,'complete'),(2,4,0,'open');", [[4,0],[8,0]]),
    ],
    'c38-sql-02': [
        ("CREATE TABLE job_events(job_id,event_id,minute,state); INSERT INTO job_events VALUES('b',1,4,'open'),('a',2,3,'ok'),('a',3,3,'fail'),('b',4,2,'old');", [['a','fail'],['b','open']]),
        ("CREATE TABLE job_events(job_id,event_id,minute,state); INSERT INTO job_events VALUES('z',3,-1,'late'),('z',2,-1,'early'),('m',9,0,'only');", [['m','only'],['z','late']]),
    ],
    'c38-sql-03': [
        ("CREATE TABLE products(id,category); CREATE TABLE sales(product_id,units,day); INSERT INTO products VALUES(1,'A'),(2,'A'),(3,'B'),(4,'C'); INSERT INTO sales VALUES(1,2,'d2'),(1,3,'d2'),(2,NULL,'d2'),(2,100,'d1'),(3,4,'d2');", [['A',5],['B',4],['C',0]]),
        ("CREATE TABLE products(id,category); CREATE TABLE sales(product_id,units,day); INSERT INTO products VALUES(9,'X'),(10,'Y'); INSERT INTO sales VALUES(9,NULL,'d2'),(10,8,'d1');", [['X',0],['Y',0]]),
    ],
    'c38-sql-04': [
        ("CREATE TABLE teams(id,name); CREATE TABLE members(id,team_id); CREATE TABLE tickets(id,member_id,priority,closed); INSERT INTO teams VALUES(1,'a'),(2,'b'),(3,'c'); INSERT INTO members VALUES(10,1),(11,1),(20,2); INSERT INTO tickets VALUES(1,10,'high',0),(2,10,'low',0),(3,11,'high',0),(4,20,'high',1);", [[1,2],[2,0],[3,0]]),
        ("CREATE TABLE teams(id,name); CREATE TABLE members(id,team_id); CREATE TABLE tickets(id,member_id,priority,closed); INSERT INTO teams VALUES(8,'x'),(7,'y'); INSERT INTO members VALUES(1,8),(2,7); INSERT INTO tickets VALUES(5,1,'high',0),(6,2,'high',0);", [[7,1],[8,1]]),
    ],
}

SQL_GOLD = {
    'c38-sql-01': "SELECT u.id,COALESCE(SUM(CASE WHEN s.state='complete' THEN s.minutes ELSE 0 END),0) AS total FROM users u LEFT JOIN sessions s ON s.user_id=u.id GROUP BY u.id ORDER BY total DESC,u.id",
    'c38-sql-02': 'WITH ranked AS (SELECT job_id,state,ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY minute DESC,event_id DESC) AS rn FROM job_events) SELECT job_id,state FROM ranked WHERE rn=1 ORDER BY job_id',
    'c38-sql-03': "SELECT p.category,COALESCE(SUM(s.units),0) AS total FROM products p LEFT JOIN sales s ON s.product_id=p.id AND s.day='d2' GROUP BY p.category ORDER BY p.category",
    'c38-sql-04': "SELECT t.id,COUNT(DISTINCT CASE WHEN k.priority='high' AND k.closed=0 THEN k.id END) AS n FROM teams t LEFT JOIN members m ON m.team_id=t.id LEFT JOIN tickets k ON k.member_id=m.id GROUP BY t.id ORDER BY n DESC,t.id",
}

PLAN_GOLD = {
    'c38-plan-01': {'order':['A','C','B','D'],'starts':[0,2,5,9],'finish_minute':11},
    'c38-plan-02': {'items':['B','C','D'],'total_cost':12,'total_score':22},
    'c38-plan-03': {'route':['S','B','A','T'],'arrival_minute':7},
    'c38-plan-04': {'assignment':[['W1','J2',2],['W2','J1',0]],'total_minutes':6},
}


def workload():
    data=strict_json(TASKS.read_text())
    tasks=data['tasks'];ids=[t['id'] for t in tasks]
    if data['schema']!='c38-quality12-v1' or len(tasks)!=12 or len(set(ids))!=12 or \
            set(ids)!=set(CODE_TESTS)|set(SQL_CASES)|set(PLAN_GOLD) or \
            data['policy']['max_output_tokens']!=3072 or data['policy']['context_tokens']!=8192:
        raise ValueError('C38 workload/validator schema invalid')
    return data


def grade(task_id,content):
    if task_id not in set(CODE_TESTS)|set(SQL_CASES)|set(PLAN_GOLD):
        raise ValueError('unknown C38 task')
    if not isinstance(content,str) or not content.strip():
        return {'status':'FAIL','reason':'empty final content'}
    content=unwrap(content)
    if task_id in CODE_TESTS:
        harness="namespace={}\nexec(compile(open('/tmp/candidate.py').read(),'/tmp/candidate.py','exec'),namespace)\n"
        harness+='exec('+repr(CODE_TESTS[task_id])+',namespace)\n'+f'print({SENTINEL!r})\n'
        result=isolated_python(content,harness,'candidate.py')
    elif task_id in SQL_CASES:
        harness="import sqlite3\nquery=open('/tmp/candidate.sql').read()\n"
        for script,expected in SQL_CASES[task_id]:
            harness+="db=sqlite3.connect(':memory:')\n"
            harness+='db.executescript('+repr(script)+')\n'
            harness+='actual=[list(x) for x in db.execute(query).fetchall()]\n'
            harness+='assert actual=='+repr(expected)+', (actual,'+repr(expected)+')\n'
            harness+='db.close()\n'
        harness+=f'print({SENTINEL!r})\n'
        result=isolated_python(content,harness,'candidate.sql')
    else:
        try: actual=strict_json(content)
        except (TypeError,ValueError) as exc:
            return {'status':'FAIL','reason':'invalid JSON: '+str(exc)}
        expected=PLAN_GOLD[task_id]
        return {'status':'PASS' if actual==expected else 'FAIL',
                'reason':None if actual==expected else 'wrong plan or tie break'}
    if 'bwrap:' in result.get('stderr_tail','') and 'Operation not permitted' in result['stderr_tail']:
        return {'status':'VALIDATOR_ENV_ERROR','reason':result['stderr_tail'][-300:]}
    return result


def self_test():
    workload();out={}
    for task_id in list(CODE_TESTS)+list(SQL_CASES)+list(PLAN_GOLD):
        gold=CODE_GOLD.get(task_id,SQL_GOLD.get(task_id))
        if gold is None: gold=json.dumps(PLAN_GOLD[task_id])
        mutant=CODE_MUTANT.get(task_id,'SELECT 1' if task_id in SQL_CASES else '{}')
        good=grade(task_id,gold);bad=grade(task_id,mutant)
        out[task_id]={'gold':good['status'],'mutant':bad['status']}
        if good['status']!='PASS' or bad['status']!='FAIL':
            raise RuntimeError(f'C38 validator self-test failed {task_id}: {out[task_id]}')
    return out


if __name__=='__main__':
    print(json.dumps(self_test(),sort_keys=True,allow_nan=False))
