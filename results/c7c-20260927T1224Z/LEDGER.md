# C7c ledger

- Bridge measurement commit `5e01697b2c7cb1602c07790bb3525866d397daa4`; original backend and model pins as in `bridge-protocol.json`.
- `c7c-p8-c4-bridge01` and `c7c-p8-c7-bridge01` each completed one 113-ID P8 prefill under E18. The full 201088-F32 output is bitwise equal. Bridge runs are excluded from timing.
- A second transient `nvidia-smi` read failed just after C4 exited; four subsequent readings and the fresh C7 preflight passed. No in-run telemetry gap or NVIDIA/Xid kernel event was found. Raw incident retained.
- Paired P8/P12 timing, session, context and quality: NOT_RUN. Next: alternating 113+32 teacher-forced pairs using the frozen C7 probe.

- G3 measurement commit `ed2510128357a99301bd7907c28661ed2af879f4`; `c7c-g3-pair1-p8`, `pair1-p12`, `pair2-p12`, `pair2-p8` completed 113+32 teacher-forced steps, E18, guards valid. Full 33-row logits are bitwise within P8 and P12; P8 prefill matches original C4 bridge.
- G3 `SHORT_FAVORABLE`: paired median T_work +3.39%, prefill +4.06%, TPOT +0.54%; both work pairs positive (+3.93%, +2.85%). GPU max 5674 MiB, RSS max 14.92 GB, cgroup peak 14.72 GB, no swap. Cross-profile logits differ as permitted.
- An immediate post-run `nvidia-smi` query failed once, recovered on next read; no in-run telemetry loss or NVIDIA/Xid event. Raw incident retained in resource summary. Next: new measurement identity for 496+32 screening; server TTFT, quality, 8K and sustained use remain NOT_RUN.
