# C130 — quality12 attempt stopped before model

**Effective status: `FAIL_HARNESS_PREMODEL_START_INVENTORY_CADENCE`.** The
frozen slots40 quality12 attempt started a real E18/zero-swap scope, but the
per-arm 60 s inventory raised `start inventory cadence gap` before the
model process was created. The runner wrote a no-replace failure receipt:
`model_launch_observed=false`, zero completed requests and no thermal or
model failure attribution. C130 does not provide a quality result.

The collector preserved 50 valid rows through elapsed49.156 s. The largest
serialized gap was1.162 s; the rejected next sample was not serialized, so
its exact duration and whether sampling or host scheduling caused it cannot
be reconstructed. The policy's maximum is1.5 s. The existing model-free
negative control `test_terminal_sampling_delay_and_second_nvme` reproduces
that a slow sample must fail the cadence gate; it passed again after this
attempt. There is no evidence that changing the gate is justified.

Frozen measurement commit:
`5673be142eb3dbf3c91ffb9a4aa2e7a5e113db9e`. The local JSONL has
SHA256 `4ef85d5af841a186f100de6c6a1adec4f881c297efa09c73b2ffe97194e75ced`;
the failure receipt hash and path are in `manifest.json`. The raw remains
local and the original decision is immutable. C100/C117 historical failures
also remain unchanged.

Next: one new C130b identity, fresh live snapshot and independent 60 s
inventory, same quality tasks and threshold. A second cadence failure would
end this retry path and require a discriminating source/timing diagnosis
before another physical attempt. No default or remote write.
