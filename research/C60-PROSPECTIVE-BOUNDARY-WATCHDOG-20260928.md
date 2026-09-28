# C60 prospective boundary watchdog

- Objective: reuse `run_bounded.py` with the same v2 resource authority as the server runner for direct C++ numeric captures. C60 has not run a 120B boundary yet.
- Base: C55 resource policy and passing C58 physical policy canary; repaired backend `aac3bbde35575044d290798a120cde038f85b670` built separately with GCC 15.3.1, CUDA 13.3 and arch 89. The C48 backend and FAIL are untouched.
- Evidence class: SOURCE_AUDITED and REPRODUZIDO_MODEL_FREE for the watchdog. The capture binary is a C48-derived wrapper restricted to layer 0/prefill0, the previously failing boundary; all model graph chunks still execute and are checked.
- Alternative: a direct C++ probe can bypass the v2 policy even though the server path passed C58. The new `--resource-protocol` path rejects legacy cap flags and checks start, monitor and final cgroup against one frozen section.
- Failure: C60 model-free scope spawned a linked five-second child, sampled resources and mapped libraries, then produced `PROSPECTIVE_ENDPOINT_TELEMETRY_MISSING` despite valid first sample 0.071 s and last-to-end 0.583 s. The original manifest is retained. The validator compared the last sample timestamp with the start endpoint bound.
- Repair and test: `tools.test_c60_monitor` reproduces those observed timestamps and checks late start, late end, wrong cap and OOM mutants. Corrected code separately tracks first and last sample. A fresh model-free C60b identity is required before any 120B boundary.
- Limits: model-free mapped libraries and monitor do not establish C57 numeric fidelity. The C60 capture restriction does not produce complete 36-layer coverage; that remains a later gate if the targeted failure passes.
- Next: C60b linked-child smoke under real E18/zero-swap scope; then freeze a new physical numeric boundary identity, OFF/ON, no performance claim.
