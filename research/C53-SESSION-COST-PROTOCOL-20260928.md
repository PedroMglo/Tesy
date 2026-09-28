# C53 — incremental session cost attribution

- Objective: use the completed C52b samples to separate server prefill and decode time, with `/proc/PID/io` counter deltas for each phase.
- Base: `38b34cdfeeac117d267f05a3073eb3f9b1fa99a8`; dedicated branch `campaign/120b-session-cost-attribution-20260928-1254utc`.
- Evidence class: exploratory model-free analysis of frozen C52b raw and C46 diagnostic summary. No new model execution.
- Alternative: high incremental latency may arise from streamed I/O, CPU wave work, overlap or another operator. Process I/O bytes alone cannot assign exclusive critical-path time.
- Method: verify parent manifest/raw hashes; interpolate monotone process `read_bytes`, `rchar` and `syscr` at request start, start plus server `prompt_ms`, and request end. Require <=3 s sample gaps. Report every row and medians over 19 incremental requests.
- Tests before analysis: three synthetic interpolation/negative tests plus six existing assistant-history tests; 9/9 passed. Frozen input and analyzer hashes in `protocol.json`.
- Decision rule: no PASS/FAIL performance threshold or causal attribution from this accounting. If bytes are substantial in both phases, the next physical test must instrument wait and overlap on the same warm-prefix workload before selecting wave versus residency/prefetch.
- Limitations: the C46 wave result is from cold513, whereas C52b is warm exact-prefix 153 IDs; neither its interval fraction nor its active-pair density transfers numerically. `/proc/PID/io` is process accounting and cannot certify NVMe physical traffic.
- Next gate: run the hash-checked analyzer once, then decide whether a bounded warm-prefix phase tracer is feasible within the remaining physical budget.
