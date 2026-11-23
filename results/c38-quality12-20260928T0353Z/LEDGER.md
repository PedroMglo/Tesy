# C38 functional qualification

- New synthetic 12-task code/SQL/planning suite and validators frozen before responses. Three profiles: P8, P12, stock20B ngl13. Model SHA and parameters are in protocol/usage-contract; all outcomes and failures will be preserved.

- `c38-stock20-init` PASS_INIT_ONLY at measurement `691db3cff129346d5e9c2b765ad624ce9665d63f`: 8.555 s, GPU 6158 MiB, cgroup peak 11.177 GB, zero swap/OOM. Forward workspace remains unknown; smoke is next.

- `c38-stock20-smoke` PASS_CAPACITY_SMOKE: one 85+32-token request, GPU 6176 MiB, cgroup peak 7.186 GB, zero swap/OOM. Longer tasks remain watched.

- `c38-stock20` PASS_COMPLETE_12_TASKS: 11/12 validator PASS, plan-01 FAIL_TRUNCATED at 3072 cap, elapsed 312.881 s. GPU peak 6202 MiB, CPU90 C, NVMe52.85 C, zero swap/OOM. P8/P12 still NOT_RUN.

- `c38-p8` FAIL_TELEMETRY: after 2/12 complete requests, monitor rejected an unrecorded out-of-range CPU effective frequency; third stream incomplete. Last valid sample CPU 88.5 C, GPU 55.0 C, NVMe 54.85 C, swap0/OOM0. P8 quality NOT_QUALIFIED; P12 NOT_RUN. No retry under C38. See p8-failure-summary/decision.
