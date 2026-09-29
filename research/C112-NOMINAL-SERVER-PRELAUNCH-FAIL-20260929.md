# C112 prelaunch failure

Objective/base: nominal128 actual-history server screen, measurement commit `0e2793e7509bfd866372fbbabd2258838ac44799`. The first command invoked the Python runner directly. `c2_server_run.run()` requires the parent process to belong to the frozen E18 systemd user scope and checks `memory.max` plus `memory.swap.max=0` before loading a model.

Observed: `c112-p1-control` returned `FAIL_RESOURCES_OR_EVIDENCE` with `GateError: frozen cgroup cap and zero swap not enforced`. Zero requests completed; no server or 120B model was launched. The receipt remains in `results/c112-nominal-server-20260929T1015Z/raw/` and its SHA is in `manifest.json`. Other arms are NOT_RUN. This is an invocation/harness failure, not evidence that E18 capacity or the model failed.

Decision: close C112 as `FAIL_LAUNCH_SCOPE_PREMODEL`. Reproduce the cgroup requirement with a small model-free subprocess in a real scope, then freeze a new identity whose launcher includes the scope command. Do not reuse C112 IDs or edit its receipt. C100 and all earlier FAILs remain unchanged. No default or remote change.
