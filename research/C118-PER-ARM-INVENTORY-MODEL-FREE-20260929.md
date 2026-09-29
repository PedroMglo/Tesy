# C118 — per-arm start inventory repair, model-free

Objective: repair the specific C117 harness omission before any new nominal153 server attempt. C117 required a 60 s inventory before **each** arm, but only collected one before the family. Its four observed timings remain diagnostic and its effective decision is `FAIL_RESOURCES_OR_EVIDENCE`; no C117 run is resumed.

Base: C117 measurement commit `dfff419540413bfeeb1d8f334c49ae7c238af8ea`, with its raw and preliminary decision preserved. Evidence class `REPRODUZIDO_MODEL_FREE`. The new `tools/c118_start_inventory.py` writes a new per-arm JSONL at ≤1.5 s gap for at least 60 s, validates CPU/GPU/NVMe, MemAvailable, GPU UUID and AC/profile on every sample, and returns a SHA receipt. It is a small helper for a **new** runner identity; it has not been integrated into, or measured with, a 120B run.

Directed tests: valid sample series passes; missing/short/gapped C117 series fail; duplicate output, a gap, GPU stop crossing and loss of AC fail in the C118 helper. The repaired C117 analyzer now rejects the actual C117 root at the first missing series. This model-free result does not certify a future full entry point or guarantee sampling cadence under load.

Decision: `HARNESS_COMPONENT_READY_MODEL_FREE`, physical and full-entrypoint gates `NOT_RUN`. Next campaign must integrate this helper before `c2_server_run.run`, add an entrypoint test proving it executes for every arm and that absence/gap blocks model load, freeze a fresh root/snapshot/measurement commit, and only then conduct a new two-pair operational nominal153 screen under an admitted budget. No threshold/resource change, backend change, remote write or default change.
