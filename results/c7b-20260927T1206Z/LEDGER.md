# C7b ledger

- Measurement commit `505c3ce1cbb5aad3f42d1b312f3d0bfdaa98b551`; original backend `1248fd8...`; P12, ub32, slots32, E18.
- New runs: `c7b-g2-p12-off01`, `c7b-g2-p12-on01`, `c7b-g2-p12-off02`. All returned 0 under guards. Five complete 201088-F32 selected logits vectors were bitwise equal OFF/ON/OFF2. OFF1/OFF2 full 33-row payload hashes also match.
- Capture: 250 numeric states and two explicit masked entries; 3675 indexed tensors, 996 equal canonical-byte slices. Structural summary: `boundary-summary.json`.
- Prior C7 attempt 01 remains `GATE_REPAIR_BLOCKED` after an unobservable aliased stage was required by its validator. One transient read-only `nvidia-smi` query failed after C7b ON; three later queries and the OFF2 preflight passed. Incident raw is preserved.
- Canonical witness replays on measurement commit `a4b72cb25f9da5317b414ee8489bac4c15501977`: layers 25–28 and 24/29, each in its own bounded E18 scope, all 42 numeric states bitwise (IDs, routing weights, FFN). Each replay lasted 1.2–1.7 s with 2–3 resource samples; this is start/end coverage, not sustained telemetry.
- Remaining 30 canonical layers, P8/P12 timing, session, context and quality: NOT_RUN. Next: remaining layers, stopping at first failure.
