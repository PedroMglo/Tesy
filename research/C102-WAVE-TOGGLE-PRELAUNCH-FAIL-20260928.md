# C102 prelaunch failure

- **Objective/base:** Same-binary C75 OFF/ON decode attribution; frozen measurement commit `8201488bcc8b1f898fbb8edce8502784b5ed4a99`.
- **Observed:** The first invocation passed `--measurement-commit 8201488`. The runner compared it to full `HEAD` and raised `GateError: C102 measurement commit/worktree/environment changed` before `server.run`. Exit code 1; `raw/` remained empty. No 120B model loaded, no thermal or numerical observation.
- **Decision:** `FAIL_HARNESS_PRELAUNCH_MODEL_NOT_LOADED`; the other three arms are `NOT_RUN`. C100's `NO_GO_CONFIRM` and all earlier FAILs are unchanged. Do not reuse the C102 run ID.
- **Next gate:** Add a model-free test for abbreviated versus full measurement commit and a new C103 identity with a full SHA, then repeat the frozen diagnostic question only if fresh preflight passes.
