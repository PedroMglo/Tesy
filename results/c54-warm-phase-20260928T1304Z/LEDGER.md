# C54 ledger

- Measurement commit: `0e8b7192fefc464e66952b178c08f17a9a0cf7de`; diagnostic backend: `2e558cb79f9184e1c87f7bc842c03fe66f7f580e`.
- Model-free build/help/NVTX smoke and host preflight passed. Idle admission: 300.05 s, PASS.
- User ordered interruption during turn01. The verified own model PID received SIGTERM. Original receipt remains `FAIL_RESOURCES_OR_EVIDENCE` with `RUN_ERROR:GateError:incomplete stream completion/usage/timings fence`. No thermal guard fired.
- One of two requests completed: turn00 2043 prompt IDs and 77 completion tokens. Turn01 and phase attribution are NOT_RUN/INCOMPLETE_EVIDENCE. Server elapsed 496.98 s before stop.
- Observed maxima: CPU 95.125 °C, GPU 63.0 °C, NVMe 55.85 °C, VRAM 5752.0 MiB, cgroup swap 0. These are partial-run observations, not a qualified performance result.
- Source/tests/protocol/preflight, compact decision and hashes committed locally for remote review. Raw trace and model are excluded from Git. No default change.
- Next: review the evidence; a fresh identity is needed to complete the warm-phase diagnostic if execution is later authorized.
