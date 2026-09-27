# C22 fresh prefix OFF/ON screen

- Base `fcdad67`; C21 idle PASS but server gate rejected missing `raw/` before model launch. C21 failure and C20 incomplete pair preserved; neither contributes timings here.
- C22 freeze created `raw/` and the wrapper/preflight verifies it before idle. Forty focused model-free tests PASS, including a missing-output-root negative. Physical preflight READY_FOR_IDLE_ADMISSION; GPU idle 12 MiB/38 C, CPU 39.625 C, NVMe 30.85 C, AC power/performance profile, E18 zero swap.
- Same C21 profile/input/thermal band/guards and prospective OFF→ON, ON→OFF order. Only second-request cache_prompt changes. Screen thresholds and three-pair confirmation policy are in protocol.json.
- Freeze command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c22_prefix_pairs.py results/c22-prefix-pairs-20260927T1937Z --freeze` on a new root containing frozen input/usage contract. Preflight: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c22_preflight.py results/c22-prefix-pairs-20260927T1937Z`.
- C15 source-only; M3 partial, M4 NOT_RUN; default unchanged. Runs pending at freeze.
