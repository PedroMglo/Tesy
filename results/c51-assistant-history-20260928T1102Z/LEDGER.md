# C51 actual assistant-history cache accounting

- New identity after C50 frozen prefix gate failed on cache_n=2044 with old prompt LCP=2043. C50 FAIL preserved.
- Source-backed prospective bound includes previous generated tokens retained in the slot. Same backend/model/input/guards and <=55/55/50 C idle admission.
- One run, no hidden retry. M4 NOT_RUN.

- C51 run PASS: 2043/2197 prompt IDs, LCP2043, cache_n2044, both final answers `48327`; first 300.754 s, second 40.380 s; second first final content 39.860 s. E18 resources PASS, CPU95 warning, no guard stop.
- M3 partial: C37 20 user-only requests and C51 2 actual assistant-history turns are separate scopes. M4 NOT_RUN/not met by observed latency. Next C52 only under a separately available administrative budget.
