#!/usr/bin/env python3
"""Grade fixed public code, SQL and JSON tasks; leave judgment cases for review."""

import argparse
import json
from pathlib import Path
import re
import resource
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "TESY_TESTS_PASSED_94027"
CODE_TESTS = {
    "eval-code-01": "assert merge_intervals([(5,7),(1,2),(2,4)]) == [(1,4),(5,7)]\nassert merge_intervals([]) == []\n",
    "eval-code-02": "assert stable_unique([3,1,3,2,1]) == [3,1,2]\nassert stable_unique([]) == []\n",
}
SQL_FIXTURES = {
    "eval-sql-01": ("CREATE TABLE sales(order_id, customer_id, amount);"
                    "INSERT INTO sales VALUES (1,1,60),(2,1,45),(3,2,90),(4,3,120);",
                    [[3, 120], [1, 105]]),
    "eval-sql-02": ("CREATE TABLE users(id,name); CREATE TABLE events(user_id,kind);"
                    "INSERT INTO users VALUES (1,'A'),(2,'B');"
                    "INSERT INTO events VALUES (1,'purchase'),(1,'view');",
                    [[1, 1], [2, 0]]),
}


def unwrap(text):
    text = text.strip()
    fenced = re.search(r"```(?:python|sql)?\s*\n(.*?)\n```", text, re.I | re.S)
    return fenced.group(1).strip() if fenced else text


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))


def isolated_python(candidate, harness, suffix):
    with tempfile.TemporaryDirectory(prefix="tesy-eval-") as tmp:
        source = Path(tmp) / suffix
        source.write_text(candidate)
        runner = Path(tmp) / "runner.py"
        runner.write_text(harness)
        command = ["bwrap", "--unshare-all", "--die-with-parent",
                   "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib64", "/lib64",
                   "--dir", "/tmp", "--proc", "/proc", "--dev", "/dev",
                   "--ro-bind", str(source), "/tmp/candidate" + source.suffix,
                   "--ro-bind", str(runner), "/tmp/runner.py", "--chdir", "/tmp",
                   "/usr/bin/python3", "-I", "-S", "/tmp/runner.py"]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=5,
                                  env={"PATH": "/usr/bin:/bin"}, preexec_fn=limits)
            success = done.returncode == 0 and done.stdout.strip().splitlines()[-1:] == [SENTINEL]
            return {"status": "PASS" if success else "FAIL", "exit_code": done.returncode,
                    "stdout_tail": done.stdout[-500:], "stderr_tail": done.stderr[-500:]}
        except subprocess.TimeoutExpired:
            return {"status": "FAIL", "reason": "validator timeout"}


def grade(task_id, content):
    if not isinstance(content, str) or not content.strip():
        return {"status": "FAIL", "reason": "no final content"}
    content = unwrap(content)
    if task_id in CODE_TESTS:
        # exec() sees only the candidate file inside the restricted namespace.
        harness = ("namespace = {}\n"
                   "exec(compile(open('/tmp/candidate.py').read(), '/tmp/candidate.py', 'exec'), namespace)\n"
                   + "exec(" + repr(CODE_TESTS[task_id]) + ", namespace)\n"
                   + f"print({SENTINEL!r})\n")
        return isolated_python(content, harness, "candidate.py")
    if task_id in SQL_FIXTURES:
        fixture, expected = SQL_FIXTURES[task_id]
        harness = ("import sqlite3\n"
                   "db = sqlite3.connect(':memory:')\n"
                   + "db.executescript(" + repr(fixture) + ")\n"
                   "query = open('/tmp/candidate.sql').read()\n"
                   "actual = [list(row) for row in db.execute(query).fetchall()]\n"
                   + "assert actual == " + repr(expected) + ", (actual, " + repr(expected) + ")\n"
                   + f"print({SENTINEL!r})\n")
        return isolated_python(content, harness, "candidate.sql")
    if task_id in ("eval-extract-01", "eval-extract-02"):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            return {"status": "FAIL", "reason": f"invalid JSON: {exc}"}
        if task_id == "eval-extract-01":
            success = (isinstance(parsed, dict) and parsed.get("invoice") == "INV-204"
                       and parsed.get("date") == "2026-09-26"
                       and isinstance(parsed.get("total"), (int, float))
                       and parsed["total"] == 12.5)
        else:
            success = parsed == ["Ada", "Cy"]
        return {"status": "PASS" if success else "FAIL", "parsed": parsed}
    return {"status": "REVIEW", "reason": "quantitative/planning criterion requires answer review"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_manifest")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    run = json.loads(Path(a.run_manifest).read_text())
    scores = []
    for item in run["results"]:
        outcome = grade(item["task_id"], item["message"].get("content"))
        scores.append({"task_id": item["task_id"], "finish_reason": item["finish_reason"],
                       "elapsed_s": item["elapsed_s"], "usage": item["usage"], **outcome})
    report = {"source_run": a.run_manifest, "scores": scores,
              "policy": "code/SQL in no-network read-only bubblewrap; JSON exact; quantitative/planning review"}
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"source_run": a.run_manifest,
                      "status_counts": {s: sum(x["status"] == s for x in scores)
                                        for s in ("PASS", "FAIL", "REVIEW")}}))


if __name__ == "__main__":
    main()
