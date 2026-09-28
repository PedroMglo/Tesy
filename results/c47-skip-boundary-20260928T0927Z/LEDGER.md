# C47 CPU parked-pair skip

- Parent: C46 diagnostic showed 71,260/708,540 active pair slots (10.057%) and 55.594 s of tagged MMID prefill without tagged I/O overlap in one 513-ID trace. These are diagnostic bounds, not a predicted gain.
- Isolated backend: `/tmp/tesy-c47-backend-20260928`, final source commit `6a2c6c1f0c1032b5567d2a8463eb9bce85df94e8`, patch `research/patches/C47-cpu-skip-parked.patch`. Original backend/control remains untouched.
- Mechanism: only CPU waves under `TESY_CPU_WAVE_SKIP_PARKED=1` send `-1` for parked IDs; native CPU MMID writes `+0` and skips their activation conversion/dot. Active IDs, weights, router output, graph shape and final masks stay the same. GPU waves retain original parking.
- Model-free: two build failures corrected before model; final build/help passed. F32/F16 operator test passed parked `+0`, active bitwise control and resident mutant. The validator passed C7b's valid 250-state capture and rejected an ON-without-sentinel mutant.
- Frozen physical boundary: OFF, ON, fresh ON on the 189+32 `log_medium` IDs, five complete logits and 250 numeric states bitwise, 2 masked N/A, E18/CPU100, 300 s idle admission each. Canonical 36-layer reference and timing are separate later gates.
- Physical runs and candidate decision: NOT_RUN at freeze. No default change.
