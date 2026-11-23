# C131 — holdout8 slots40

Objective: test whether C75 waves ON/slots40 loses any task solved by the slots32 control on eight new, balanced code/data/planning tasks frozen before either arm answered.

Base/measurement commit: `3a695ca412b4198e3405b2054fb450bb7193350f`. Analyzer source: `46a8bd2`. The workload and grader were frozen in `c7843b79784b3516cff145ef88c8c991eab5437e`. Control and candidate used the same original GGUF, medium, context8192, E18 and zero workload swap; the only profile difference was slots32 versus slots40.

Evidence class: MEDIDO_NO_TARGET. The independent revalidation in `analysis.json` passed both receipts, raw hashes, inventory/launch/resource gates and the eight sandboxed validators. Control 8/8, candidate 8/8. Official input token arrays and all eight complete assistant messages match between arms. This is a bounded functional result; it does not establish general quality equivalence or causal timing.

Control raw SHA256 `a291015ac56c6b0b8e43a2df9f832c6895e34c21576d3139473cb6ddda887806`; candidate raw SHA256 `47672fd3a346cdf5a5fc04f128ebae53dacf27119e168839c9ef92d78ae9d8e4`. Analysis SHA256 `409321461ce305bd44d9fdf785a0f8d94251f5d7a3507c5331b5c6b65b9f1dd4`. The raw stays local.

The maximum observed cgroup charges were 13,297,516,544 and 15,750,131,712 bytes; both scopes reported zero swap. Previous C130 FAIL and C100 NO_GO remain unchanged.

Decision: `PASS_HOLDOUT_8_OF_8_NO_QUALITY_LOSS` in this scope. M3 diverse/active session remains NOT_RUN; M4 remains NOT_MET on measured warm latency/decode. Next discriminant is a varied 20-request session with actual assistant history and active load on slots40, frozen before responses.
