# C20 exact-prefix paired screen checkpoint

- Objective: compare second 641-ID request latency with P12 exact-prefix cache OFF/ON; C19 mechanism observation was the alternative to a pure wave-critical-path diagnosis.
- Base/measurement commits: C19 `30dfb1d`; C20 OFF `dae7261be9b7f66fbfd0485e9ea6e130d6745f05`; C20 ON idle `a9f3f2ea9886ab583a6a23126529c79f1fa2107d`.
- Evidence class: one qualified unpaired OFF server run and one complete no-model idle-admission failure. Frozen input/protocol, receipts and raw hashes are in `results/c20-prefix-pairs-20260927T1857Z/`.
- OFF first 513+4 request 80.263 s; second 641+4 93.931 s, cache_n 0/0, CPU maximum 95.125 C with no observed ACPI Processor cooling. No paired gain exists.
- ON idle admission stopped at its frozen 900 s cap. End CPU/GPU 41.625/39 C versus first OFF baseline 45.75/43 C; strict ±2/±3 C baseline rule was unsatisfied. ON model runs: zero. Later C20 arms: NOT_RUN.
- Decision: `THERMAL_PREFLIGHT_BLOCKED`. No corruption/thermal-limit inference and no timing claim from this incomplete pair. C9/C10b/C13/C14/C17 CPU95 stops remain `FAIL_PROTOCOL_THERMAL_GUARD` in their original receipts. M3 partial mechanism only; M4 NOT_RUN; C15 source-only, uncompiled, unmeasured.
- Next discriminating gate: new C21 identity with fresh OFF/ON arms, prospective cool-start matching band and the same backend/input/guards. The historical C20 OFF is not reused for the C21 speed calculation.
