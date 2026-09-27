# C7 P12 minimum-forward capacity protocol

Objective: distinguish lazy init-only reservation from actual forward residency. The G1 admission was measured on commit `f46bc59d84e469312a9654604d425982ece9c940`; its evidence commit is `983b3a796268fa8b23feafaa17e850ce12812c04`. The source and exact settings of `c7_profile_probe` remain unchanged. This is a new, prospective diagnostic identity with a single 113-ID external decode and no teacher forcing. The elapsed time is excluded from performance screening.

The executable rule is `results/c7-20260927T1130Z/capacity-protocol.json`. P12 must complete without nonfinite logits, swap, OOM, telemetry loss or guards, and show GPU total at most 6500 MiB, cgroup peak at most 16.5 GiB, and RSS at most 16 GiB to admit longer work. A failure closes this unit and remains in raw. G2 numeric fidelity, performance, session and functional outcomes are NOT_RUN at this freeze.
