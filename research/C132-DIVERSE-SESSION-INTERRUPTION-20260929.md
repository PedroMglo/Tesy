# C132 — varied session attempt stopped at output cap

The prospectively frozen slots40 20-turn session launched after a valid 60 s inventory. Turn04 generated exactly 512 tokens, the frozen cap. The fifth request began; the operator sent SIGINT to the verified runner PID/start ticks/scope, and the own server stopped. Decision: `FAIL_OUTPUT_CAP_INTERRUPTED_OPERATOR`. No 20-turn, 60-minute, active-block or diverse-session PASS is claimed.

The preexisting server runner's `KeyboardInterrupt` path did not write its terminal raw JSON or wrapper receipt. The launch, inventory, tokenization, samples and stderr are preserved locally, hashed in `interruption.json`. The stderr confirms turn04's 512-token eval. The sample maxima are diagnostic only because terminal receipt validation did not run. No thermal failure is attributed.

Base/measurement `21143aa4ca3efa52adf8f2c1203f192847469bde`. Output cap was fixed at512 before any answer; it will not be raised retrospectively for C132. Charge900 s conservatively to the epoch, including the 60 s inventory, launch and interruption. C100, C117 and C130 FAILs remain unchanged.

Next discriminant: make the next runner stop at cap while preserving the offending response in raw, then freeze a new shorter context-balanced workload and cap under a new unit identity. If that model-free repair fails, pivot without another physical retry.
