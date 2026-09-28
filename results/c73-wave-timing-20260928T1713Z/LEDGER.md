# C73 P12 wave skip timing screen

- Measurement `38ad974f178e98b324c72ddf06262ab53287979c`; backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`. Command: `PYTHONPATH=tools python3 tools/c73_wave_timing_run.py run results/c73-wave-timing-20260928T1713Z --measurement-commit 38ad974f178e98b324c72ddf06262ab53287979c`.
- Eight fresh arms passed: cold513 pairs OFF→ON, ON→OFF; retained-KV incremental154 pairs in same order. All 33 full logits bitwise within and across wave arms.
- Median paired T_work gain: cold513 55.98%, incremental154 39.47%; prefill gain 62.64%/52.14%; decode32 gain 0.84%/1.60%. CPU max 95.125 C warning, GPU 65 C, VRAM total 5688 MiB, workload swap 0; no resource stop.
- C48/C61/C66 FAILs remain. Confirmation, server bridge, quality and M4 are NOT_RUN. Incremental case retains KV after 2043 unmeasured conditioning IDs; it is not server exact-prefix timing.
