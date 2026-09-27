# C21 exact-prefix paired screen

- Base `12c8c1f`; new identity after C20 ON idle admission blocked at 900 s, with no model run. C20 OFF is historical and excluded from C21 gains.
- Same P12/8K/E18 zero-swap original backend, model and C13 513/641-ID synthetic prompts; only second-request `cache_prompt` varies. CPU95 warning, CPU100 stop; GPU80/NVMe70 and memory guards unchanged.
- Four frozen arms: OFF→ON; ON→OFF. New prospective idle maximum 50/50/45 C CPU/GPU/NVMe throughout continuous 300 s, then start temperature match to first arm within ±5/5/3 C. Admission timeout 900 s. No warming or power/fan policy manipulation.
- Primary second-request gain is `100*(OFF-ON)/OFF` by pair. Screen: median ≥20%, both positive, first-cold median gain ≥−5%, matching outputs, cache and resource gates. Confirmation, if screen passes, needs three new pairs.
- Model-free command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c17_idle_window tools.test_c21_thermal_match tools.test_c18_cpu_telemetry tools.test_c9_server_admission tools.test_c9_prefix_normalize tools.test_c2_gate` — 39 PASS.
- Preflight: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c21_preflight.py results/c21-prefix-pairs-20260927T1927Z` — READY_FOR_IDLE_ADMISSION. Prior C20 full model SHA reused only after exact dev/inode/size/mtime/ctime match; per-arm admission rechecks metadata.
- M3 partial prefix mechanism only; M4 NOT_RUN; C15 source-only, uncompiled and unmeasured. Default unchanged.
