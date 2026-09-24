# n-cpu-moe sweep failed campaign

Campaign: `results/n-cpu-moe-sweep-20260923T220215Z`

Status:

`FAIL_SERVER_EXIT_BEFORE_HEALTH`

Observed sequence:

- `n-cpu-moe=0`: completed.
- `n-cpu-moe=4`: `llama-server` exited before `/health` PASS.
- Sweep stopped fail-closed.
- Remaining points were NOT_RUN.

The output root is preserved and was not reused.

No Pareto, speedup, cache-benefit, transfer-byte or >RAM conclusion follows.
