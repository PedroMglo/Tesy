# C70 full wave boundary

- Measurement commit `1151213c88c7b3527a5c3aa7797d00bfbc531b8a`; C66 diagnostic backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`.
- Commands: `PYTHONPATH=tools python3 tools/c70_full_boundary_run.py run results/c70-full-wave-boundary-20260928T1652Z --measurement-commit 1151213c88c7b3527a5c3aa7797d00bfbc531b8a --arm off` and `--arm on`. Both E18 runs passed.
- Same-profile OFF/ON: 250 numeric states × 6 core stages, 2 masked, five complete logits and 996 byte witnesses per arm, bitwise. ON parked CPU pairs used 80,800 `-1` sentinels with zero masks.
- C48/C61/C66 FAILs preserved. Canonical references, ON repetition, timing, quality and M4 are NOT_RUN. Next: resident canonical layer gate.
