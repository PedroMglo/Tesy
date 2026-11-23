#!/usr/bin/env python3
"""Prospectively frozen eight-task synthetic holdout validators."""

import json
from pathlib import Path

from c2_gate import strict_json
from grade_tasks import SENTINEL, isolated_python, unwrap


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT/'workloads/c131_holdout8.json'

CODE_TESTS = {
 'c131-code-01': "assert rle_pairs([])==[]\na=[2,2,-1,-1,2];assert rle_pairs(a)==[(2,2),(-1,2),(2,1)];assert a==[2,2,-1,-1,2]\nassert rle_pairs([5])==[(5,1)]\nassert rle_pairs([0,0,0])==[(0,3)]",
 'c131-code-02': "assert window_peaks([2,1,3,0],2)==[2,3,3]\nassert window_peaks([4,-2],1)==[4,-2]\nassert window_peaks([1,2],3)==[]\na=[3,1,2];assert window_peaks(a,3)==[3] and a==[3,1,2]",
 'c131-code-03': "assert uncovered_spans([],0,4)==[(0,4)]\na=[(8,12),(1,3),(3,5)];assert uncovered_spans(a,0,10)==[(0,1),(5,8)] and a==[(8,12),(1,3),(3,5)]\nassert uncovered_spans([(-5,2),(1,7)],0,5)==[]\nassert uncovered_spans([(3,3),(4,1)],2,6)==[(2,6)]\nassert uncovered_spans([(1,4)],5,5)==[]",
}

CODE_GOLD = {
 'c131-code-01': "def rle_pairs(xs):\n out=[]\n for x in xs:\n  if out and out[-1][0]==x: out[-1]=(x,out[-1][1]+1)\n  else: out.append((x,1))\n return out",
 'c131-code-02': "def window_peaks(xs,width):\n return [max(xs[i:i+width]) for i in range(len(xs)-width+1)]",
 'c131-code-03': "def uncovered_spans(spans,lo,hi):\n if hi<=lo:return []\n cover=sorted((max(lo,a),min(hi,b)) for a,b in spans if b>a and max(lo,a)<min(hi,b))\n out=[];cur=lo\n for a,b in cover:\n  if a>cur:out.append((cur,a))\n  cur=max(cur,b)\n if cur<hi:out.append((cur,hi))\n return out",
}

CODE_MUTANT = {
 'c131-code-01': 'def rle_pairs(xs): return [(x,1) for x in xs]',
 'c131-code-02': 'def window_peaks(xs,width): return [sum(xs[i:i+width]) for i in range(len(xs)-width+1)]',
 'c131-code-03': 'def uncovered_spans(spans,lo,hi): return [(lo,hi)] if hi>lo else []',
}

SQL_CASES = {
 'c131-sql-01': [
  ("CREATE TABLE employees(id,team);CREATE TABLE shifts(employee_id,minutes,day);INSERT INTO employees VALUES(1,'A'),(2,'A'),(3,'B'),(4,'C');INSERT INTO shifts VALUES(1,5,'d3'),(1,7,'d3'),(2,NULL,'d3'),(2,99,'d2'),(3,4,'d3');",[['A',12],['B',4],['C',0]]),
  ("CREATE TABLE employees(id,team);CREATE TABLE shifts(employee_id,minutes,day);INSERT INTO employees VALUES(1,'X'),(2,'Y');INSERT INTO shifts VALUES(1,0,'d3'),(2,9,'d1');",[['X',0],['Y',0]])],
 'c131-sql-02': [
  ("CREATE TABLE scores(player,round,points,entry_id);INSERT INTO scores VALUES('a',1,10,1),('a',2,10,2),('a',2,10,3),('b',7,9,4),('b',8,8,5);",[['a',10,2],['b',9,7]]),
  ("CREATE TABLE scores(player,round,points,entry_id);INSERT INTO scores VALUES('z',1,-1,3),('z',0,-1,4),('q',5,0,1);",[['q',0,5],['z',-1,1]])],
 'c131-sql-03': [
  ("CREATE TABLE projects(id);CREATE TABLE tasks(id,project_id,state);INSERT INTO projects VALUES(1),(2),(3),(4);INSERT INTO tasks VALUES(1,1,'closed'),(2,2,'open'),(3,3,NULL),(4,3,'closed');",[[1],[3],[4]]),
  ("CREATE TABLE projects(id);CREATE TABLE tasks(id,project_id,state);INSERT INTO projects VALUES(7),(8);INSERT INTO tasks VALUES(1,8,'open'),(2,8,'closed');",[[7]])],
}

SQL_GOLD = {
 'c131-sql-01': "SELECT e.team,COALESCE(SUM(CASE WHEN s.day='d3' THEN s.minutes ELSE 0 END),0) AS total_minutes FROM employees e LEFT JOIN shifts s ON s.employee_id=e.id GROUP BY e.team ORDER BY e.team",
 'c131-sql-02': "WITH ranked AS (SELECT player,points,round,ROW_NUMBER() OVER (PARTITION BY player ORDER BY points DESC,round DESC,entry_id DESC) AS rn FROM scores) SELECT player,points,round FROM ranked WHERE rn=1 ORDER BY player",
 'c131-sql-03': "SELECT p.id FROM projects p WHERE NOT EXISTS(SELECT 1 FROM tasks t WHERE t.project_id=p.id AND t.state='open') ORDER BY p.id",
}

PLAN_GOLD = {
 'c131-plan-01': {'items':['A','B'],'total_units':11,'total_cost':14},
 'c131-plan-02': {'route':['S','B','C','T'],'arrival_minute':6},
}


def workload():
    data = strict_json(TASKS.read_text())
    tasks = data['tasks']; ids = [t['id'] for t in tasks]
    if data['schema']!='c131-holdout8-v1' or len(tasks)!=8 or len(set(ids))!=8 or \
       set(ids)!=set(CODE_TESTS)|set(SQL_CASES)|set(PLAN_GOLD) or \
       [t['category'] for t in tasks].count('code')!=3 or \
       [t['category'] for t in tasks].count('sql_data')!=3 or \
       [t['category'] for t in tasks].count('planning')!=2 or \
       data['policy']['max_output_tokens']!=3072 or data['policy']['context_tokens']!=8192:
        raise ValueError('C131 holdout schema/validator mismatch')
    return data


def grade(task_id, content):
    if task_id not in set(CODE_TESTS)|set(SQL_CASES)|set(PLAN_GOLD):
        raise ValueError('unknown holdout task')
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
        good,bad=grade(task_id,gold),grade(task_id,mutant)
        out[task_id]={'gold':good['status'],'mutant':bad['status']}
        if good['status']!='PASS' or bad['status']!='FAIL':
            raise RuntimeError(f'C131 validator self-test failed {task_id}: {out[task_id]}')
    return out


if __name__=='__main__':
    print(json.dumps(self_test(),sort_keys=True,allow_nan=False))
