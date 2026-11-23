# C56 analysis of incomplete C54 trace

- Objective: extract a bounded diagnostic from C54 raw without changing C54's interrupted status or claiming a complete second response.
- Base: `fbcb84d0e4e21403c61893b329aa6a6102ca3b55`; C54 measurement commit `0e8b7192fefc464e66952b178c08f17a9a0cf7de` and source `2e558cb79f9184e1c87f7bc842c03fe66f7f580e`.
- Evidence class: DIAGNOSTIC. C54 raw/report and compact files were hash checked against their original manifest. A new local SQLite export of the existing Nsight report is raw and remains outside Git.
- Observation: two closed warm prefill decode NVTX ranges have union 26.982 s. Tagged MMID union is 16.303 s, tagged read union 9.917 s, tagged upload union 1.104 s, and MMID/read-upload overlap is 1.000 s. Of 1610 warm wave markers, 1287 have no active pair; 20720 of 196000 pair slots are active. These are instrumented interval measurements, not a causal speedup bound.
- Alternative: the tagged MMID spans could overlap other untagged work or serialization; read/upload tags are not independent physical NVMe traffic. The forced 165 s inter-request gap also changes the warm regime.
- Decision: retain C54 `INTERRUPTED_BY_OWNER`, incomplete second API result and original FAIL receipt. The closed phase can guide the next experiment, but cannot complete the C54 bridge. Any future profiler run needs explicit request/phase markers and its own identity.
- Tests and limits: `tools/c56_analyze_partial.py` selected the server PID and closed warm intervals from a new SQLite export. Full response, cache accounting, timing under uninstrumented production, and causal removable fraction are NOT_RUN.
- Next gate: finish policy canary and C57 fidelity boundary. Only recollect warm attribution if it changes the choice between waves and residence.
