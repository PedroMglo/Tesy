# C131 — prospective eight-task holdout

Objective: test whether the confirmed C75 waves-ON/slots40 profile loses
functional tasks relative to a contemporary C75 waves-ON/slots32 control.
The eight prompts in `workloads/c131_holdout8.json` are **new** and were
fixed before either arm's response: three code, three SQLite/data and two
planning tasks. Both arms use identical medium/context8192, temperature0,
seed42, natural stop, max3072 output tokens,600 s/task, one process per arm,
E18 and workload swap0. Only expert slots32 versus slots40 change.

The grader has eight gold-positive and eight mutant-negative model-free
checks. Each code answer is executed in the existing isolated Python gate;
SQL answers run on two frozen in-memory databases; planning answers are
checked against exact JSON solutions and tie rules. The tasks, cases,
validators and caps are hashed in each prospective protocol. No prompts
were selected from candidate outputs.

Order: control then candidate. Each arm requires its own 60 s start
inventory, actual-Popen freshness, C75 mapped-library identity, valid
official token arrays, natural finish for all eight requests, resource
receipt and grader completion. Quality comparison is per task: the
candidate must pass every task passed by control; full holdout PASS
requires all eight candidate tasks PASS. A control task failure remains
visible and does not automatically block measuring the candidate.
This is a quality check, not a paired performance benchmark.

Reserve two times (3600 s server+60 s inventory),600 s closure and3600 s
for a diverse active session. New raw remains under the epoch20 GiB cap.
The C130 premodel failure, C130b quality12 PASS, C129 performance
confirmation and historical C100/C117 outcomes remain separate. No
default/main/remote write.
