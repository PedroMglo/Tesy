# C67 no-op observer

- Tesy measurement `ac5f911e973821570e40fa38be22f3fe49f458b3`; C66 diagnostic backend unchanged. Only intervention from the C7 plain probe: register a callback that returns false without tensor access.
- `python3 tools/c67_noop_observer_run.py run results/c67-noop-observer-20260928T1628Z --measurement-commit ac5f911e973821570e40fa38be22f3fe49f458b3` passed one P12/189+32 process. All 33 logits rows were bitwise equal to the preserved C66 plain output. No invalid ID, swap, OOM or guard stop.
- This single pass shows callback registration alone did not reproduce C66 in this run. Tensor selection/read work or a timing-sensitive race remains possible. C48/C61/C66 failures stay unchanged; no wave timing or adoption claim.
- Raw 26852235 B/10 files with hashes in `manifest.json`, local only. Next: isolate callback selection versus tensor reads model-free before another waves physical gate.
