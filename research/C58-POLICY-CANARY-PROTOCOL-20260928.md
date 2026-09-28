# C58 short resource-policy canary

- Objective: verify the prospective C55 resource authority under a single bounded 120B load and short forward, without making a performance claim.
- Base: C52b session backend `c3759bad92c0e6f71bb936afea9b0a162fb83f76`, same binary and mapped library hashes as its verified raw. Model stat must equal C52b's full-SHA-verified file. C58 runner source is frozen before the physical unit.
- Evidence class before execution: SOURCE_AUDITED and REPRODUZIDO_MODEL_FREE only.
- Intervention: v2 monitor/admission/receipt policy. The backend, P12/slots32/ub32, 8192 context, full SWA, F16 KV and preload ON command remain from C52b. A new synthetic one-token API request exercises forward and completion; it is not a C52b workload repeat or quality result.
- Resource envelope: fresh 60 s inventory, E18 single cgroup cap 19327352832 B, swap.max/current zero, frozen device/host start and stop values from the new snapshot. Only one arm and no retries. Timeout 300 s including load; per-request timeout 180 s. Server port 18367.
- Alternative: a model-free smoke can miss allocation or sensor behavior under 120B. C58 distinguishes that from a policy that merely parses data correctly.
- Decision rule: PASS only with one complete finite response, valid return code, mapped backend libraries, process/cgroup identity, no guard event or swap, complete raw and receipt. Any failure is preserved under C58 and diagnosed under a new identity. The run gives no speedup or M4 claim.
- Tests before freeze: `tools.test_c58_canary` verifies no-model freeze, cap uniqueness and no-replace; `tools.test_c55_runner_entrypoint` exercises a child and negative receipts. Full model-free suite must pass. C48 FAIL remains independent.
- Next gate if PASS: C57 targeted boundary/reference before timing. Placement P14 accounting can proceed model-free regardless of C57's physical result.
