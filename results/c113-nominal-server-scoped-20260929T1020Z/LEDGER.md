# C113 ledger

- New campaign after C112 premodel scope failure. Scoped launcher is frozen and reproduced model-free; workload and numerical profile unchanged.
- Two screen pairs control→candidate; candidate→control. Fresh E18 policy and 3720 s worst-case epoch admission. Five model-free tests pass; direct unscoped and scoped wrong-SHA negatives reject at distinct gates.
- Control `c113-p1-control` PASS: two complete requests; 2043/2197 official prompt IDs, cache_n2044; CPU peak95.125 °C (warning, below100 stop), GPU64 °C, NVMe57.85 °C, swap0. The candidate's 300 s matched-start window expired with NVMe38.85 °C versus required ≤35.85 °C. Candidate model NOT_RUN, second pair NOT_RUN; no server gain exists. Decision `INCOMPLETE_MATCH_NOT_ADMITTED`; raw and failure receipt preserved. No remote publication or default change.
