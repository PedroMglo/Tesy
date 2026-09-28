# C91: server canary stopped before model load

- **Objective/base:** admit C75 8K P12 server load and one-token forward under E18. Source `ed11e8914188022db228cf72364a5d2804faa993`; measurement `2d9a72e550a1788fd7e353294f090e3287db2e5e`.
- **Observed:** direct invocation returned `FAIL_RESOURCES_OR_EVIDENCE` with `frozen cgroup cap and zero swap not enforced`. No raw files or 120B process were created. The direct shell cgroup had unbounded `memory.max` and `memory.swap.max`. **MEDIDO_NO_TARGET** for the harness stop; model behavior **NOT_RUN**.
- **Diagnosis:** `c2_server_run.run` explicitly requires the caller to already be inside the frozen scope. A new model-free `systemd-run --user --scope` child reported `memory.max=19327352832` and `memory.swap.max=0`. **REPRODUZIDO_MODEL_FREE** for launcher correction. This does not convert C91 to a PASS.
- **Alternative/limits:** no conclusion about C75 model load, forward capacity, fidelity, thermal state or server latency. C48/C78 historical failures unchanged.
- **Decision:** preserve C91 FAIL and freeze a new identity using the demonstrated outer scope command; no hidden retry or guard change.
