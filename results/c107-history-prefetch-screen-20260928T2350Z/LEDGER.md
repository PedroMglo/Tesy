# C107 ledger

- Model-free: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c107_history_prefetch_screen` (2 passed); `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c107_history_prefetch_screen.py` on C105 trace.
- Recent 1/2/4 routed-token histories covered **0** absent-primary expert demands; 8 covered **2/724**. No 120B run or prefetch implementation. This rejects only recent-router replay as a useful prefetch policy on the frozen 189+32 trace.
- Physical NVMe savings, lead time, warm-session behavior and M4 NOT_RUN. C100/other FAILs unchanged. Next: test source/trace evidence for bounded overlap or pivot backend, with correctness before timing.
