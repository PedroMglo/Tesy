# Async steady-tail execution preparation: lint repair

Date: 2026-09-24

Objective: clear the model-free test gate before the prospective 81-pair physical campaign.

Base commit: `f34e2f07abcf5150b3444d1c93f038d7ca6f92f2`.
Base tree: `de703fa3add68ad071f536265ef98977b1fb07e5`.

Evidence class: `REPRODUCED_MODEL_FREE`; physical campaign `NOT_RUN` at this record.

The first focused gate stopped at Ruff I001 in
`tests/test_mixed_residency_async_tail_order.py`: the `json` and `pathlib`
imports were out of order. The only code change reorders those imports.
There is no native C++ or scheduling change. The prospective sample count,
inputs, thresholds, stop conditions and decision labels remain as frozen in
`MIXED-RESIDENCY-ASYNC-TAIL-ORDER-PROTOCOL-20260924.md`.

Alternatives considered: proceed after the lint failure, or modify the
measurement protocol. Both were rejected because the former violates the
stated gate and the latter is unnecessary for an import-order defect.

Tests: focused shell syntax, Ruff, compileall and pytest PASS (35 tests);
full Ruff, compileall, shell syntax and pytest PASS (197 tests); `git diff
--check` PASS. The initial failed Ruff invocation remains recorded in the
conversation and was not counted as a pass.

Decision: commit this repair before building or measuring. The resulting
new commit and tree become the campaign source identity; the native build
sidecar must use that commit. No physical performance conclusion follows
from these model-free checks.

Limitations: physical host, model, histogram, backend, CUDA build, runtime
resources and order-conditioned latency still require their separate gates.

Next discriminating gate: verify immutable inputs and physical host, rebuild
CUDA at the new HEAD, then run the 81-pair tail/order campaign once under
the unchanged prospective protocol.
