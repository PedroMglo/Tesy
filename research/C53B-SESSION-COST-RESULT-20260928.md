# C53b — result of model-free session accounting

- Objective: describe where C52b's incremental request time and process-read accounting occur, preserving the failed C53 endpoint policy.
- Base/measurement commit: `201016a` on `campaign/120b-session-cost-attribution-20260928-1254utc`. No model was loaded.
- Evidence class: diagnostic interpolation over C52b's completed raw request timers and process samples, both matched to its manifest hashes.
- Observation: among 18 complete incremental 153-ID windows, median `/proc/PID/io read_bytes` was 37.21 GiB/request, with 15.52 GiB assigned to prefill and 21.62 GiB to decode. Corresponding time medians over the 19 incremental requests were 25.92 s and 16.29 s. The last request ended 0.4355 s after the final sample; its counter is a lower bound and that window is excluded from I/O medians.
- Alternative: these bytes can overlap compute; `/proc/PID/io` does not isolate expert traffic, CPU/GPU destinations, cache hits or physical NVMe writes/reads. C46's cold513 MMID interval result concerns a different workload. Neither mechanism has won a causal ranking.
- Decision: `DIAGNOSTIC_ACCOUNTING_ONLY`; M3 C52b scope unchanged, M4 unmet, default unchanged.
- Tests: 9 model-free tests passed for C53b; frozen parent/analyzer hashes passed. C53 `FAIL_HARNESS_ENDPOINT_POLICY` remains recorded. Physical tracing: NOT_RUN.
- Next gate: C54 source/static feasibility for a warm exact-prefix 153-ID tagged-I/O and MMID interval diagnostic on the C35 backend. Its measurement must remain diagnostic and stay within the remaining physical budget.
