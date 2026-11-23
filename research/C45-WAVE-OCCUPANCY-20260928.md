# C45: CPU wave occupancy, diagnostic scope

- Objective: bound tagged CPU `MUL_MAT_ID` wall occupancy in one 513-ID cold P12 server request before investing in wave compaction.
- Base: investigation measurement commit `90e5604b7a952c29c7dcb847e3ede37171ffa35a`; diagnostic backend `1691fb65a00c963ec3aa64a5b66a1b951de52d15`; model SHA `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`.
- Evidence: C45 profiler run passed E18 resources and matched the four greedy output tokens from C43 original/C15 plain. The 12,300 tagged CPU MMID intervals have union 58.307 s, 73.324% of C43 original completed prefill 79.520 s. Pread union is 22.394 s; MMID and pread overlap 2.436 s. Profiled prefill 79.861 s is diagnostic only.
- Alternative: the interval label may include work outside the prefill or outside the streamed expert path. Occupancy does not identify removable, exclusive critical-path time. Per-wave active-pair density and phase alignment are unmeasured.
- Decision: the frozen <20% deprioritization condition did not fire. Phase-align intervals and count active pairs before implementing compaction. C15 remains diagnostic instrumentation; no speedup or numeric full-logit claim.
- Tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c45_nvtx_analyze.py` included interval-union positive/negative controls, actual-process NVTX identity and receipt/hash bridges. `tools/c45_close.py` checked cgroup, guards, output bridge and manifest. Full-logit bitwise, compaction, causality and M4 are NOT_RUN.
- Failures: C43 and C44 profiler prelaunch failures remain recorded. No C45 guard failure; CPU reached 95.125 °C warning below the prospective 100 °C stop, with zero cgroup swap/OOM.
- Next gate: new diagnostic identity with explicit prefill phase boundaries and per-wave active-pair counters, one bounded 513-ID request only if model-free checks and remaining budget permit it. Use the result to bound exclusive removable time or pivot to residency/session work.
