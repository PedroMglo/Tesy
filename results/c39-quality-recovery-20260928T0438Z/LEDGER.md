# C39 quality recovery

- New campaign identity after C38 P8 telemetry FAIL. Same frozen tasks/model/backend/profiles/output cap; CPU clock monitor repair commit a0df14f is the only harness change. C38 FAIL remains unchanged; stock20 comparator is reused with SHA.

- `c39-p8` FAIL_ORCHESTRATOR_INTERRUPTION: control-plane restart killed runner/watchdog, own server survived and was stopped; no complete raw receipt or terminal sample. Last valid sample 2281.000 s, CPU max89.125 C, GPU56 C, NVMe56.85 C, swap/OOM0. Charge 2400 s unreceipted runtime plus separately counted 320.557 s idle. P8 quality INCOMPLETE_EVIDENCE, P12 NOT_RUN.
