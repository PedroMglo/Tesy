# C33 C15 tracer feasibility

- Freeze only for isolated build and model-free NVTX collection. Original backend control remains clean; C15 source commit `1691fb6` in separate `/tmp` worktree. No 120B execution in this unit. If smoke passes, a new protocol is required before any profiler run against the model.
