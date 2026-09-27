# C7c ledger

- Bridge measurement commit `5e01697b2c7cb1602c07790bb3525866d397daa4`; original backend and model pins as in `bridge-protocol.json`.
- `c7c-p8-c4-bridge01` and `c7c-p8-c7-bridge01` each completed one 113-ID P8 prefill under E18. The full 201088-F32 output is bitwise equal. Bridge runs are excluded from timing.
- A second transient `nvidia-smi` read failed just after C4 exited; four subsequent readings and the fresh C7 preflight passed. No in-run telemetry gap or NVIDIA/Xid kernel event was found. Raw incident retained.
- Paired P8/P12 timing, session, context and quality: NOT_RUN. Next: alternating 113+32 teacher-forced pairs using the frozen C7 probe.
