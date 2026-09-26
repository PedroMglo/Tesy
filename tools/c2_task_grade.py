#!/usr/bin/env python3
"""Frozen C2 task validators; all code/SQL execution uses a no-network bwrap scope."""

import argparse
import json
from pathlib import Path

from c2_gate import strict_json
from c2_server_run import CORE_IDS
from grade_tasks import isolated_python, unwrap, SENTINEL


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "workloads/c2_tasks.json"

CODE_TESTS = {
    "c2-dev-code-01": "assert dedupe_last([2,1,2,3,1]) == [2,3,1]\nassert dedupe_last([]) == []\nassert dedupe_last(['x','x']) == ['x']",
    "c2-eval-code-01": "assert compress_runs([]) == []\nassert compress_runs([1,1,2,1]) == [(1,2),(2,1),(1,1)]\nassert compress_runs([[1],[1],[2]]) == [([1],2),([2],1)]\nassert compress_runs(['a']) == [('a',1)]",
    "c2-eval-code-02": "assert interval_subtract((1,10),[(3,5),(8,12)]) == [(1,2),(6,7)]\nassert interval_subtract((1,3),[]) == [(1,3)]\nassert interval_subtract((2,2),[(2,2)]) == []\nassert interval_subtract((-2,4),[(0,1),(1,3)]) == [(-2,-1),(4,4)]\nassert interval_subtract((1,5),[(8,10)]) == [(1,5)]",
    "c2-eval-code-03": "assert topo_lex(['c','b','a'], [('a','c')]) == ['a','b','c']\nassert topo_lex(['a','b'], [('a','b'),('a','b')]) == ['a','b']\nassert topo_lex(['a','b'], [('a','b'),('b','a')]) == []\nassert topo_lex(['z','x','y'], []) == ['x','y','z']\nassert topo_lex([], []) == []",
}

CODE_GOLD = {
    "c2-dev-code-01": "def dedupe_last(xs):\n return [x for i,x in enumerate(xs) if x not in xs[i+1:]]",
    "c2-eval-code-01": "def compress_runs(xs):\n out=[]\n for x in xs:\n  if out and out[-1][0] == x: out[-1]=(x,out[-1][1]+1)\n  else: out.append((x,1))\n return out",
    "c2-eval-code-02": "def interval_subtract(base,cuts):\n lo,hi=base\n alive=set(range(lo,hi+1))\n for a,b in cuts: alive.difference_update(range(a,b+1))\n out=[]\n for x in sorted(alive):\n  if out and x == out[-1][1]+1: out[-1]=(out[-1][0],x)\n  else: out.append((x,x))\n return out",
    "c2-eval-code-03": "def topo_lex(nodes,edges):\n import heapq\n adj={x:set() for x in nodes}; deg={x:0 for x in nodes}\n for a,b in edges:\n  if b not in adj[a]: adj[a].add(b); deg[b]+=1\n q=[x for x in nodes if deg[x]==0]; heapq.heapify(q); out=[]\n while q:\n  a=heapq.heappop(q); out.append(a)\n  for b in adj[a]:\n   deg[b]-=1\n   if deg[b]==0: heapq.heappush(q,b)\n return out if len(out)==len(nodes) else []",
}

CODE_MUTANT = {
    "c2-dev-code-01": "def dedupe_last(xs): return list(dict.fromkeys(xs))",
    "c2-eval-code-01": "def compress_runs(xs): return [(x,xs.count(x)) for x in set(xs)]",
    "c2-eval-code-02": "def interval_subtract(base,cuts): return [base]",
    "c2-eval-code-03": "def topo_lex(nodes,edges): return sorted(nodes)",
}

SQL_CASES = {
    "c2-dev-sql-01": [
        ("CREATE TABLE customers(id,name); CREATE TABLE orders(id,customer_id,amount,status); INSERT INTO customers VALUES (1,'A'),(2,'B'); INSERT INTO orders VALUES (1,1,5,'paid'),(2,1,NULL,'paid'),(3,2,9,'open');", [[1,5],[2,0]]),
        ("CREATE TABLE customers(id,name); CREATE TABLE orders(id,customer_id,amount,status); INSERT INTO customers VALUES (4,'Q');", [[4,0]])],
    "c2-eval-sql-01": [
        ("CREATE TABLE customers(id,name); CREATE TABLE orders(id,customer_id,status,amount); INSERT INTO customers VALUES (1,'A'),(2,'B'),(3,'C'),(4,'D'); INSERT INTO orders VALUES (1,1,'paid',7),(2,1,'refund',99),(3,2,'paid',NULL),(4,3,'paid',10),(5,3,'paid',1);", [[3,11],[1,7],[2,0],[4,0]]),
        ("CREATE TABLE customers(id,name); CREATE TABLE orders(id,customer_id,status,amount); INSERT INTO customers VALUES (8,'X'),(7,'Y'); INSERT INTO orders VALUES (1,8,'paid',5),(2,7,'paid',5),(3,7,'pending',200);", [[7,5],[8,5]])],
    "c2-eval-sql-02": [
        ("CREATE TABLE events(user_id,day,kind); INSERT INTO events VALUES (1,'d1','login'),(1,'d1','login'),(1,'d1','purchase'),(2,'d1','login'),(3,'d2','purchase'),(NULL,'d2','login');", [['d1',1],['d2',0]]),
        ("CREATE TABLE events(user_id,day,kind); INSERT INTO events VALUES (5,'d1','login'),(5,'d2','purchase'),(6,'d2','login'),(6,'d2','purchase'),(7,'d2','login'),(7,'d2','purchase');", [['d1',0],['d2',2]])],
    "c2-eval-sql-03": [
        ("CREATE TABLE products(id,category,price); INSERT INTO products VALUES (1,'A',10),(2,'A',10),(3,'A',8),(4,'A',7),(5,'B',NULL),(6,'B',5),(7,'C',3),(8,'C',2);", [['A',8],['C',2]]),
        ("CREATE TABLE products(id,category,price); INSERT INTO products VALUES (1,'X',1),(2,'X',4),(3,'X',2),(4,'Y',9),(5,'Y',9),(6,'Z',NULL);", [['X',2]])],
}

SQL_GOLD = {
    "c2-dev-sql-01": "SELECT c.id, COALESCE(SUM(CASE WHEN o.status='paid' THEN o.amount ELSE 0 END),0) FROM customers c LEFT JOIN orders o ON o.customer_id=c.id GROUP BY c.id ORDER BY c.id",
    "c2-eval-sql-01": "SELECT c.id, COALESCE(SUM(CASE WHEN o.status='paid' THEN o.amount ELSE 0 END),0) AS total FROM customers c LEFT JOIN orders o ON o.customer_id=c.id GROUP BY c.id ORDER BY total DESC,c.id",
    "c2-eval-sql-02": "SELECT d.day, COUNT(DISTINCT l.user_id) FROM (SELECT DISTINCT day FROM events) d LEFT JOIN events l ON l.day=d.day AND l.kind='login' AND l.user_id IS NOT NULL AND EXISTS (SELECT 1 FROM events p WHERE p.day=d.day AND p.user_id=l.user_id AND p.kind='purchase') GROUP BY d.day ORDER BY d.day",
    "c2-eval-sql-03": "WITH distinct_prices AS (SELECT DISTINCT category,price FROM products WHERE price IS NOT NULL) SELECT p.category,p.price FROM distinct_prices p WHERE (SELECT COUNT(*) FROM distinct_prices q WHERE q.category=p.category AND q.price>p.price)=1 ORDER BY p.category",
}

SQL_MUTANT = {key: "SELECT 1" for key in SQL_CASES}

JSON_GOLD = {
    "c2-dev-quant-01": {"initial":48,"final":44,"lost_net":4},
    "c2-dev-plan-01": {"order":["A","B","C"],"finish_minute":6},
    "c2-eval-quant-01": {"p_defective":"19/120","p_B_given_defective":"14/19"},
    "c2-eval-quant-02": {"final_liters":495,"average_net_liters_per_min":0.5},
    "c2-eval-plan-01": {"order":["A","C","B","D"],"starts":[0,2,4,7],"finish_minute":9},
    "c2-eval-plan-02": {"items":["B","D","E"],"total_weight":10,"score":19},
    "c2-eval-spec-01": {"failed_ids":["k5","k7"],"success_count":5},
    "c2-eval-spec-02": {"region":"apac","retention_days":7,"alert":"on"},
}


def grade_text(task_id, content):
    if not isinstance(content, str) or not content.strip():
        return {"status":"FAIL","reason":"missing final content"}
    content = unwrap(content)
    if task_id in CODE_TESTS:
        harness = ("namespace={}\nexec(compile(open('/tmp/candidate.py').read(),'/tmp/candidate.py','exec'),namespace)\n"
                   + "exec(" + repr(CODE_TESTS[task_id]) + ",namespace)\n"
                   + f"print({SENTINEL!r})\n")
        result = isolated_python(content, harness, "candidate.py")
    elif task_id in SQL_CASES:
        cases = SQL_CASES[task_id]
        harness = "import sqlite3\nquery=open('/tmp/candidate.sql').read()\n"
        for script, expected in cases:
            harness += ("db=sqlite3.connect(':memory:')\n"
                        + "db.executescript(" + repr(script) + ")\n"
                        + "actual=[list(x) for x in db.execute(query).fetchall()]\n"
                        + "assert actual==" + repr(expected) + ",(actual," + repr(expected) + ")\n"
                        + "db.close()\n")
        harness += f"print({SENTINEL!r})\n"
        result = isolated_python(content, harness, "candidate.sql")
    elif task_id in JSON_GOLD:
        try:
            actual = strict_json(content)
        except (ValueError, TypeError) as exc:
            return {"status":"FAIL","reason":f"invalid JSON: {exc}"}
        expected = JSON_GOLD[task_id]
        if type(actual) is not dict or set(actual) != set(expected) or \
           any(type(actual[key]) is not type(value) or actual[key] != value
               for key, value in expected.items()):
            return {"status":"FAIL","reason":"wrong fields or values"}
        return {"status":"PASS"}
    else:
        raise ValueError(f"unknown task ID: {task_id}")
    if "bwrap:" in result.get("stderr_tail", "") and "Operation not permitted" in result["stderr_tail"]:
        return {"status":"VALIDATOR_ENV_ERROR","reason":result["stderr_tail"][-300:]}
    return result


def validate_suite():
    workload = strict_json(TASKS.read_text())
    if set(workload) != {"schema_version","policy","tasks"} or workload["schema_version"] != "c2-tasks-v1":
        raise ValueError("invalid task suite schema")
    tasks = workload["tasks"]
    ids = [x["id"] for x in tasks]
    if len(tasks) != 16 or len(set(ids)) != 16 or sum(x["split"] == "dev" for x in tasks) != 4 or \
       sum(x["split"] == "eval" for x in tasks) != 12:
        raise ValueError("wrong task counts or duplicate IDs")
    if set(ids) != set(CODE_TESTS)|set(SQL_CASES)|set(JSON_GOLD):
        raise ValueError("unvalidated or missing task")
    if any(set(x) != {"id","split","category","prompt"} or not x["prompt"] for x in tasks):
        raise ValueError("malformed task")
    return workload


def reference_check():
    validate_suite()
    results = {}
    for task_id in list(CODE_TESTS)+list(SQL_CASES)+list(JSON_GOLD):
        gold = CODE_GOLD.get(task_id, SQL_GOLD.get(task_id))
        if gold is None:
            gold = json.dumps(JSON_GOLD[task_id])
        mutant = CODE_MUTANT.get(task_id, SQL_MUTANT.get(task_id))
        if mutant is None:
            wrong = dict(JSON_GOLD[task_id]); key = next(iter(wrong))
            wrong[key] = "WRONG" if type(wrong[key]) is not str else "wrong"
            mutant = json.dumps(wrong)
        good = grade_text(task_id, gold)
        bad = grade_text(task_id, mutant)
        results[task_id] = {"gold":good["status"],"mutant":bad["status"]}
        if good["status"] != "PASS" or bad["status"] != "FAIL":
            raise RuntimeError(f"validator failed its reference/mutant test: {task_id}: {results[task_id]}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--run-manifest")
    p.add_argument("--output")
    a = p.parse_args()
    if a.self_test:
        print(json.dumps(reference_check()))
        return
    if not a.run_manifest or not a.output:
        p.error("--run-manifest and --output required unless --self-test")
    tasks = validate_suite()["tasks"]
    by_id = {x["id"]:x for x in tasks}
    run = strict_json(Path(a.run_manifest).read_text())
    if run.get("schema_version") == "c2-server-raw-v1":
        if run["preflight"]["config"]["suite"] != "c2core8":
            raise ValueError("C2 grader requires frozen core8 suite")
        expected = list(CORE_IDS)
        rows = run["results"]
        if run["stop_reasons"] or run["returncode"] != 0:
            raise ValueError("incomplete/failed C2 server run")
        if [x["id"] for x in rows] != expected or \
           [x["source_task_id"] for x in rows] != expected:
            raise ValueError("missing/duplicate/out-of-order C2 task result")
        mode = "c2core8"
    else:
        expected = [x["id"] for x in tasks if x["split"] == run["split"]]
        rows = run["results"]
        if [x["task_id"] for x in rows] != expected:
            raise ValueError("missing/duplicate/out-of-order task result")
        mode = "legacy"
    scores = []
    for row in rows:
        task_id = row["source_task_id"] if mode == "c2core8" else row["task_id"]
        outcome = grade_text(task_id, (row["message"] or {}).get("content"))
        if mode == "c2core8" and outcome["status"] == "VALIDATOR_ENV_ERROR":
            raise RuntimeError(f"isolated validator unavailable for {task_id}")
        status = "FAIL_TRUNCATED" if mode == "c2core8" and row["finish_reason"] != "stop" else outcome["status"]
        item = {"task_id":task_id,"status":status,
                "finish_reason":row["finish_reason"], "detail":outcome}
        if mode == "c2core8":
            usage = row.get("usage") or {}
            item.update({"prompt_tokens":usage.get("prompt_tokens"),
                         "completion_tokens_total":usage.get("completion_tokens"),
                         "request_wall_s":row["ended_s"]-row["started_s"],
                         "reasoning_characters":len((row["message"] or {}).get("reasoning_content") or ""),
                         "final_characters":len((row["message"] or {}).get("content") or ""),
                         "reasoning_tokens":None,"final_tokens":None,
                         "first_token_s":None,"first_final_s":None})
        scores.append(item)
    report = {"source_run":a.run_manifest,"schema_version":"c2-task-grade-v2" if mode == "c2core8" else "legacy-task-grade-v1",
              "scores":scores,
              "pass_count":sum(x["status"] == "PASS" for x in scores),
              "validator_policy":"frozen synthetic code/SQL bwrap assertions and strict exact JSON",
              "latency_limit":"nonstreamed C2 API; TTFT and first final content NOT_MEASURED; reasoning/final token split not exposed" if mode == "c2core8" else None}
    with Path(a.output).open("x") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"pass_count":report["pass_count"],"n":len(scores)}))


if __name__ == "__main__":
    main()
