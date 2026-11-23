# C46 phase and wave-density diagnostic

- Objective: determine whether sparse parked token-expert pairs coexist with material tagged CPU MMID occupancy during the actual cold 513-ID prefill.
- Base: investigation `acaf1d5` (C45 close); diagnostic backend C15 `1691fb65a00c963ec3aa64a5b66a1b951de52d15`, changed in isolated C46 source commit `005e8ff8dd264a2fdecd6dd99e42580d8d2674dc`. Original backend remains the C43 control.
- Evidence before model: C45's MMID union 58.307 s across all phases, greedy four-token output bridge, C46 build and model-free NVTX range/mark smoke. These do not prove removable work.
- Hypothesis: a low active/all pair fraction causes avoidable parked computation in the completed prefill. Alternative: tagged MMID is mainly necessary active work, overlaps other work, or compaction overhead erases savings.
- Frozen investment screen: active/all prefill wave pairs <=0.75 and MMID prefill occupancy without overlap with tagged pread/upload >=20% of C43 original completed prefill. Both conditions justify only a prototype with a prospective canonical reference; neither predicts speedup.
- Physical gate: one new cold 513-ID run under E18 and CPU100 prospective guard, 300 s idle admission, mapped libraries, C43 greedy output bridge, full resource telemetry, no retry. Nsight times are diagnostic and cannot be promoted to timing gain.
- Tests/NOT_RUN: model-free build/help/NVTX smoke passed; C46 physical run, phase alignment, active density, full-logit bitwise and wave compaction NOT_RUN at freeze.
- Failure policy: stop the unit on source/identity, output, profiler, cgroup, telemetry or guard failure and preserve its receipt. No retry within C46.
- Next gate: analyze phase-clipped MMID and wave marks; if the investment screen passes and budget permits, design a separate compaction profile/reference; otherwise pivot to session/prefix or residency work.
