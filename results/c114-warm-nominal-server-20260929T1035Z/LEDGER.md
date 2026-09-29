# C114 ledger

- Prospective candidate-first server screen after C113 cold matching stopped. Same synthetic actual-history workload and v2 resource limits; order candidate→control, control→candidate, matching 3/3/2 °C within each pair.
- Fresh inventory and E18 scope test passed. Five model-free tests and scoped wrong-SHA negative passed. Existing epoch admits 3720 s worst case at freeze.
- Candidate ON PASS: 2043 cold prompt IDs and 153 new IDs on the incremental request, cache_n2044, both responses complete. First final cold92.961 s, incremental25.115 s; incremental decode3.571 tok/s. CPU peak95 °C warning, GPU62 °C, NVMe52.85 °C, swap0. Control never launched: 300 s match ended NVMe37.85 °C versus ≤35.85 °C required. Pair2 NOT_RUN; no paired server gain. Decision `INCOMPLETE_MATCH_NOT_ADMITTED`; old failures retained, no remote/default change.
