# C81 session latency gap

- Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c81_latency_gap.py`; C52b raw and C74 compact hashes verified against manifests. No model run.
- C52b, 19 incremental requests: median prefill 25.925 s, first final 41.464 s, decode 3.753 tok/s. The arithmetic first-final minus prefill residual is median 15.761 s and exceeds 10 s in 19/19 requests.
- Even with prefill set to zero while holding that residual fixed, the proposed 10 s M4 target is unmet. Reaching 6 tok/s from this decode median needs a 37.46% TPOT reduction. C74 wave probe decode-time gain was about 1.44%; it is a separate workload/profile.
- This is an inference for prioritizing tests, not a C75 server measurement. Next: decode demand/wait and bounded residency trace after 8K numeric admission. M4 NOT_MET; default unchanged.
