# C62 P14 capacity admission

- Objective: determine whether P14/slots32/ub32 on the unchanged C35 session backend can load at 8192 context and complete one bounded cold prompt under E18. This tests capacity, not a speedup, fidelity or M4 claim.
- Base: C61 result commit `100483a` and C59 tensor accounting. C61 invalid-ID FAIL belongs to the separate C57 backend and remains unchanged.
- Evidence class at freeze: `SOURCE_AUDITED` and `ESTIMADO` from C59. P14 predicted GPU total 6623.981 MiB before workspace changes; it requires measured admission under the current 7676 MiB total-device stop.
- Intervention: only `-ngl 12` to `-ngl 14` relative to the pinned C52b session backend. Context8192, slots32, ub32, preload ON, KV/SWA, threads, model and server settings remain fixed. First process loads/context only; if it passes, a fresh second process handles the historical C17 synthetic ~513-token prompt with cap4. No performance comparison is inferred without contemporary P12 controls.
- Alternative: extra CUDA layers exceed allocator/workspace or cgroup headroom despite C59's static bound. First failed init or forward ends C62, with no automatic retry.
- Gates: fresh 60-second host inventory, prospective single resource authority, E18 zero-swap systemd scope, mapped libraries, model stat and raw hashes, complete receipt and output, GPU total/temp, RAM/cgroup/PSI, AC/performance and NVMe guards. A clean measurement commit precedes both processes. The forward prompt count band is 480–540 official tokens, matching the historical synthetic input definition.
- Tests/NOT_RUN now: policy entrypoint and receipt model-free tests from C55/C60 remain applicable; C62 live init/forward, numerical reference, timing, diverse session and M4 are `NOT_RUN` until the freeze and admission execute.
- Next gate after capacity PASS: same-profile numerical boundary/reference for P14 before paired performance; compare P12/P14 under one cap and exact workload only then.
