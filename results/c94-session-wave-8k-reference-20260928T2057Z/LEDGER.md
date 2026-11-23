# C94 8K resident FFN reference

- Source `7555fd7444cc89d1ff1052d7ab524ce811bfcb7f`; witness measurement `4054e5cc766d591c28348d4b309b68cf60f58cd4`; remaining measurement `20fb9b11517d33cf78d1cce1eb6af856e5054ec0`. C71 reference tests 2/2 passed; C93 ON raw verified against manifest before references.
- Six witness layers 25–28,24,29 passed first (42 numeric rows). Remaining 30 passed after a separate clean checkpoint (208 numeric and 2 masked rows). Total 36 layer loads, 250 numeric comparisons bitwise and 2 `N/A_MASKED`.
- E16 per-layer cap, zero workload swap/stop; maximum cgroup peak 4,133,711,872 B, GPU 1734 MiB, CPU 61.375 °C. Sum of bounded layer elapsed 65.432 s; not a model latency metric.
- C48/C78/C91 FAILs preserved. Attention/KV independent reference, fresh ON repetition, server latency, usefulness and M4 remain NOT_RUN.
- Next: fresh-process ON repeat of the C93 8K profile, then server bridge only if bitwise.
