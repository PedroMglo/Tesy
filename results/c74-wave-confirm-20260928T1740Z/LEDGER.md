# C74 P12 wave skip confirmation

- Measurement commit `6dfc6848646d1100133f78aaa06a05cb9fed7394`; backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`. Command: `PYTHONPATH=tools python3 tools/c74_wave_confirmation.py run results/c74-wave-confirm-20260928T1740Z --measurement-commit 6dfc6848646d1100133f78aaa06a05cb9fed7394`.
- Twelve new fresh arms passed: three alternating pairs per case. Complete 33-logit outputs matched bitwise within and between OFF/ON. Median paired T_work gain: cold513 55.86%, retained-KV incremental154 39.19%; median prefill gains 62.50%/51.95%; decode32 gains 1.13%/1.44%.
- CPU max 95.25 C warning, GPU 65 C, VRAM total 5688 MiB, workload swap 0; no stop. Cold pairs 1 and 3 exceeded at least one start-temperature matching band; all incremental pairs matched.
- C48/C61/C66 FAILs remain. Server bridge, quality and M4 are NOT_RUN. This is n_ctx4096/preload-OFF teacher-forced probe, not API timing.
