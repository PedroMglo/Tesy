# C68 observer continuation repair

- Measurement `5c18e428034d2cfc87d1b0aa1627947174190e84`; C66 diagnostic backend unchanged. C60 source was copied, and the out-of-scope branch now returns `!ask` so delivery of a selected node cannot cancel the scheduler split.
- Model-free scheduler graph: false delivery left downstream at intermediate 3; true delivery produced 5. `python3 tools/c68_capture_repair_run.py run results/c68-callback-repair-20260928T1636Z --measurement-commit 5c18e428034d2cfc87d1b0aa1627947174190e84` passed observer OFF, complete layer0 C61 schema and five full logits bitwise against C66 plain.
- No invalid expert ID, swap/OOM/guard stop. Raw 5145788 B/42 local files, hashes in `manifest.json`.
- Scope: harness repair OFF only. C48/C61/C66 FAILs unchanged. Wave ON, remaining canonical layers, timing and quality NOT_RUN. Next: new wave ON targeted boundary using corrected observer and frozen C68 OFF control.
