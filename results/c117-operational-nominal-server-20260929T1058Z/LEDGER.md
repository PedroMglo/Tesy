# C117

- Freeze: `dfff419540413bfeeb1d8f334c49ae7c238af8ea`; two pairs C35/C75 ON, 2043 cold IDs then 153 new IDs with 2044 cached, E18/swap0. Scope and five model-free tests passed.
- Runs: `c117-p1-control`, `c117-p1-candidate`, `c117-p2-candidate`, `c117-p2-control` all passed with natural stop and guards valid. Abbreviated-SHA prelaunch rejection preserved in raw; no model loaded in it.
- Effective gate: FAIL_RESOURCES_OR_EVIDENCE. The frozen 60 s per-arm inventory was missing; C55's one family inventory does not satisfy it. `decision.json` is the preserved preliminary misclassification; `decision-effective.json` and `reaudit.json` are authoritative. The repaired analyzer rejects the missing series.
- Descriptive, unqualified paired observations: warm first final +36.201%, cold first final +69.153%; warm decode −0.180%. Candidate warm first final ~25.21 s, decode ~3.54 tok/s. No screen promotion, confirmation/M4/default change.
- Limits: pair1 start temperatures differed materially; two pairs, synthetic task, no free-server full-logit capture or diverse/sustained quality. C100 NO_GO remains.
- Next: repair/test per-arm inventory, then a new valid nominal153 screen; confirmation only after that. A phase-marked warm153 trace remains the decode mechanism discriminant. Raw and manifest remain local.
