# C47 runtime assertion, preserved

- Objective/base: numeric OFF → ON → fresh ON capture for CPU parked-pair skip, measurement commit `ec035213ecf0f92e3b4e98c40fb943afec58e5b7`, backend `6a2c6c1f0c1032b5567d2a8463eb9bce85df94e8`.
- Observed: OFF completed 189+32 and valid 250-state capture in 71.895 s. ON exited by SIGABRT after 15.817 s during context reserve, before any prefill output. stderr contains `ggml-backend.cpp:584: GGML_ASSERT(device) failed`. ON repeat was not run.
- Source diagnosis: `ggml_backend_cpu_buffer_type()` deliberately sets its device field to NULL. The C47 device test passed that NULL to `ggml_backend_dev_type()`. This is a source and observed-assert explanation, not a numerical mismatch. CPU max 73.75 °C, GPU max 47 °C, NVMe max 40.85 °C, swap/OOM zero; no thermal guard stop.
- Decision: `FAIL_RESOURCES_OR_EVIDENCE` with specific reason `RUNTIME_ASSERT_CPU_BUFFER_TYPE_DEVICE_NULL`. No fidelity, canonical or timing claim from C47. Preserve raw/receipt and both build failures recorded in C47's model-free evidence.
- Alternative: even after fixing device detection, skipped outputs could differ or affect later arithmetic; the C47 failure did not test that. C48 must have a new source commit, build, operator gate, preflight, root and contemporary OFF/ON/ON controls.
- Tests/NOT_RUN: C47 F32/F16 model-free operator passed; OFF full capture passed; ON numeric, ON repeat, 36 canonical loads, timing, M4 are NOT_RUN. Existing C43/C44/C41b and old CPU95 failures remain unchanged.
