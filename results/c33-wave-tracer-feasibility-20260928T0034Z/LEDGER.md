# C33 C15 tracer feasibility

- Freeze only for isolated build and model-free NVTX collection. Original backend control remains clean; C15 source commit `1691fb6` in separate `/tmp` worktree. No 120B execution in this unit. If smoke passes, a new protocol is required before any profiler run against the model.

- CMake configure/build `llama-server` PASS on isolated C15 commit; binary and raw log hashes in `build-summary.json`. `llama-server --help` PASS without model. Direct sandbox `nsys profile` returned EPERM; local escalated trace captured one `C33_NVTX_SMOKE` 100.084 ms range. `nsys stats --report nvtx_sum` PASS. No model execution, no wave timing claim. C34 numerical bridge and bounded phase-aware profile is next.
